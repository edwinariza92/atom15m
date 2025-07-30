import time
import pandas as pd
import numpy as np
from binance.client import Client
from binance.enums import *
from datetime import datetime
import csv
import os
import requests

# ======== CONFIGURACIÓN ========
api_key = 'Lw3sQdyAZcEJ2s522igX6E28ZL629ZL5JJ9UaqLyM7PXeNRLDu30LmPYFNJ4ixAx'
api_secret = 'Adw4DXL2BI9oS4sCJlS3dlBeoJQo6iPezmykfL1bhhm0NQe7aTHpaWULLQ0dYOIt'
symbol = 'ATOMUSDT'
intervalo = '15m'
riesgo_pct = 0.03  # 3% de riesgo por operación
umbral_volatilidad = 0.02  # ATR máximo permitido para operar
# ===============================

client = Client(api_key, api_secret)
client.API_URL = 'https://fapi.binance.com/fapi'  # FUTUROS

TELEGRAM_TOKEN = '7578395267:AAHJ7Evtjobc5gfUAx_lCEdUtZ3TI7m0Xh4'
TELEGRAM_CHAT_ID = '1715798949'

def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"❌ Error enviando notificación Telegram: {e}")

def obtener_datos(symbol, intervalo, limite=100):
    klines = client.futures_klines(symbol=symbol, interval=intervalo, limit=limite)
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume',
                                       'close_time', 'quote_asset_volume', 'number_of_trades',
                                       'taker_buy_base', 'taker_buy_quote', 'ignore'])
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    return df[['close', 'high', 'low']]

def calcular_senal(df):
    df['ma'] = df['close'].rolling(window=20).mean()
    df['std'] = df['close'].rolling(window=20).std()
    df['upper'] = df['ma'] + 2 * df['std']
    df['lower'] = df['ma'] - 2 * df['std']
    df['ma50'] = df['close'].rolling(window=50).mean()  # MA50 para filtro de tendencia

    if len(df) < 51:
        return 'neutral'
    close_prev = df['close'].iloc[-2]
    close_now = df['close'].iloc[-1]
    upper_prev = df['upper'].iloc[-2]
    upper_now = df['upper'].iloc[-1]
    lower_prev = df['lower'].iloc[-2]
    lower_now = df['lower'].iloc[-1]
    ma50_now = df['ma50'].iloc[-1]

    # Señal long: cruce arriba banda superior y precio sobre MA50
    if close_prev <= upper_prev and close_now > upper_now and close_now > ma50_now:
        return 'long'
    # Señal short: cruce abajo banda inferior y precio bajo MA50
    elif close_prev >= lower_prev and close_now < lower_now and close_now < ma50_now:
        return 'short'
    else:
        return 'neutral'

def calcular_cantidad_riesgo(saldo_usdt, riesgo_pct, distancia_sl):
    riesgo_usdt = saldo_usdt * riesgo_pct
    if distancia_sl == 0:
        return 0
    cantidad = riesgo_usdt / distancia_sl
    return round(cantidad, 3)

def ejecutar_orden(senal, symbol, cantidad):
    try:
        side = SIDE_BUY if senal == 'long' else SIDE_SELL
        try:
            orden = client.futures_create_order(
                symbol=symbol,
                side=side,
                type=ORDER_TYPE_MARKET,
                quantity=cantidad
            )
        except Exception as e:
            print(f"❌ Error al crear la orden de mercado: {e}")
            return None, None

        # Verifica que la posición realmente se abrió
        info_pos = client.futures_position_information(symbol=symbol)
        if not info_pos or float(info_pos[0]['positionAmt']) == 0:
            print("❌ La orden fue enviada pero no se abrió posición. Puede ser por cantidad mínima o error de Binance.")
            return None, None

        precio = float(info_pos[0]['entryPrice'])
        print(f"✅ Operación {senal.upper()} ejecutada a {precio}")
        return precio, cantidad

    except Exception as e:
        print(f"❌ Error inesperado al ejecutar operación: {e}")
        return None, None

def registrar_operacion(fecha, tipo, precio_entrada, cantidad, tp, sl, resultado=None, pnl=None):
    archivo = 'registro_operaciones_atom.csv'
    existe = os.path.isfile(archivo)
    with open(archivo, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not existe:
            writer.writerow(['Fecha', 'Tipo', 'Precio Entrada', 'Cantidad', 'Take Profit', 'Stop Loss', 'Resultado', 'PnL'])
        writer.writerow([fecha, tipo, precio_entrada, cantidad, tp, sl, resultado if resultado else "", pnl if pnl is not None else ""])

def obtener_precisiones(symbol):
    info = client.futures_exchange_info()
    cantidad_decimales = 3
    precio_decimales = 3
    for s in info['symbols']:
        if s['symbol'] == symbol:
            for f in s['filters']:
                if f['filterType'] == 'LOT_SIZE':
                    step_size = float(f['stepSize'])
                    cantidad_decimales = abs(int(np.log10(step_size)))
                if f['filterType'] == 'PRICE_FILTER':
                    tick_size = float(f['tickSize'])
                    precio_decimales = abs(int(np.log10(tick_size)))
    return cantidad_decimales, precio_decimales

def calcular_atr(df, periodo=14):
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['close'] = df['close'].astype(float)
    df['tr'] = df[['high', 'low', 'close']].apply(
        lambda row: max(row['high'] - row['low'], abs(row['high'] - row['close']), abs(row['low'] - row['close'])), axis=1)
    df['atr'] = df['tr'].rolling(window=periodo).mean()
    return df['atr'].iloc[-1]

def notificar_pnl(symbol):
    trades = client.futures_account_trades(symbol=symbol)
    if trades:
        ultimo_trade = trades[-1]
        pnl = float(ultimo_trade.get('realizedPnl', 0))
        enviar_telegram(f"🔔 Posición cerrada en {symbol}. PnL: {pnl:.4f} USDT")
        return pnl
    else:
        enviar_telegram(f"🔔 Posición cerrada en {symbol}. No se pudo obtener el PnL.")
        return None

def detectar_resultado_cierre(symbol, precio_entrada, tp, sl):
    trades = client.futures_account_trades(symbol=symbol)
    if not trades:
        return ""
    # Busca el último trade de cierre (reduceOnly=True)
    for trade in reversed(trades):
        if trade.get('reduceOnly', False):
            precio_ejecucion = float(trade['price'])
            # Compara el precio de ejecución con TP y SL
            if abs(precio_ejecucion - tp) < abs(precio_ejecucion - sl):
                return "TP"
            else:
                return "SL"
    return ""

# ============ LOOP PRINCIPAL ============
ultima_posicion_cerrada = True
datos_ultima_operacion = {}

while True:
    df = obtener_datos(symbol, intervalo)

    if len(df) < 51:
        print("⏳ Esperando más datos...")
        time.sleep(60)
        continue

    senal = calcular_senal(df)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Señal detectada: {senal.upper()}")

    info_pos = client.futures_position_information(symbol=symbol)
    pos_abierta = float(info_pos[0]['positionAmt']) if info_pos else 0.0

    # --- 1. Detectar cierre de posición y notificar/registrar resultado ---
    if pos_abierta == 0 and not ultima_posicion_cerrada and datos_ultima_operacion:
        pnl = notificar_pnl(symbol)
        try:
            resultado = detectar_resultado_cierre(
                symbol,
                datos_ultima_operacion["precio_entrada"],
                datos_ultima_operacion["tp"],
                datos_ultima_operacion["sl"]
            )
        except Exception as e:
            resultado = ""
            enviar_telegram(f"❌ Error detectando resultado de cierre: {e}")

        registrar_operacion(
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            datos_ultima_operacion["senal"],
            datos_ultima_operacion["precio_entrada"],
            datos_ultima_operacion["cantidad_real"],
            datos_ultima_operacion["tp"],
            datos_ultima_operacion["sl"],
            resultado=resultado,
            pnl=pnl
        )
        if resultado == "TP":
            enviar_telegram(f"🎉 ¡Take Profit alcanzado en {symbol}! Ganancia: {pnl:.4f} USDT")
        elif resultado == "SL":
            enviar_telegram(f"⚠️ Stop Loss alcanzado en {symbol}. Pérdida: {pnl:.4f} USDT")
        elif resultado:
            enviar_telegram(f"ℹ️ Posición cerrada en {symbol}. Resultado: {resultado}, PnL: {pnl:.4f} USDT")
        ultima_posicion_cerrada = True
        datos_ultima_operacion = {}

    # --- 2. Cancelar órdenes TP/SL pendientes si no hay posición abierta ---
    if pos_abierta == 0:
        ordenes_abiertas = client.futures_get_open_orders(symbol=symbol)
        for orden in ordenes_abiertas:
            if orden['type'] in ['STOP_MARKET', 'TAKE_PROFIT_MARKET']:
                try:
                    client.futures_cancel_order(symbol=symbol, orderId=orden['orderId'])
                    print(f"🗑️ Orden pendiente cancelada: {orden['type']}")
                except Exception as e:
                    print(f"❌ Error al cancelar orden pendiente: {e}")
                    enviar_telegram(f"❌ Error al cancelar orden pendiente: {e}")

    # --- 3. Evitar duplicar posiciones en la misma dirección ---
    if (senal == 'long' and pos_abierta > 0) or (senal == 'short' and pos_abierta < 0):
        print("⚠️ Ya hay una posición abierta en la misma dirección. No se ejecuta nueva orden.")
        time.sleep(60)
        continue

    # --- 4. Abrir nueva operación si hay señal y no hay posición abierta ---
    if senal in ['long', 'short'] and pos_abierta == 0:
        atr = calcular_atr(df)
        if atr > umbral_volatilidad:
            print("Mercado demasiado volátil, no se opera.")
            time.sleep(60)
            continue

        balance = client.futures_account_balance()
        saldo_usdt = next((float(b['balance']) for b in balance if b['asset'] == 'USDT'), 0)

        precio_actual = float(df['close'].iloc[-1])
        if senal == 'long':
            sl = precio_actual - atr * 1.2
            tp = precio_actual + atr * 2
            distancia_sl = atr * 1.2
        else:
            sl = precio_actual + atr * 1.2
            tp = precio_actual - atr * 2
            distancia_sl = atr * 1.2

        cantidad_decimales, precio_decimales = obtener_precisiones(symbol)
        cantidad = calcular_cantidad_riesgo(saldo_usdt, riesgo_pct, distancia_sl)
        cantidad = round(cantidad, cantidad_decimales)
        sl = round(sl, precio_decimales)
        tp = round(tp, precio_decimales)

        print(f"💰 Saldo disponible: {saldo_usdt} USDT | Usando {cantidad} contratos para la operación ({riesgo_pct*100:.1f}% de riesgo, SL={sl:.4f}, TP={tp:.4f})")

        precio_entrada, cantidad_real = ejecutar_orden(senal, symbol, cantidad)

        if precio_entrada:
            ultima_posicion_cerrada = False
            datos_ultima_operacion = {
                "senal": senal,
                "precio_entrada": precio_entrada,
                "cantidad_real": cantidad_real,
                "tp": tp,
                "sl": sl
            }

            # Cancelar órdenes TP/SL abiertas antes de crear nuevas
            ordenes_abiertas = client.futures_get_open_orders(symbol=symbol)
            for orden in ordenes_abiertas:
                if orden['type'] in ['STOP_MARKET', 'TAKE_PROFIT_MARKET']:
                    try:
                        client.futures_cancel_order(symbol=symbol, orderId=orden['orderId'])
                    except Exception as e:
                        print(f"❌ Error al cancelar orden previa: {e}")
                        enviar_telegram(f"❌ Error al cancelar orden previa: {e}")

            try:
                # Crear TP/SL según la dirección de la señal
                if senal == 'long':
                    client.futures_create_order(
                        symbol=symbol,
                        side='SELL',
                        type='TAKE_PROFIT_MARKET',
                        stopPrice=tp,
                        quantity=cantidad_real,
                        reduceOnly=True
                    )
                    client.futures_create_order(
                        symbol=symbol,
                        side='SELL',
                        type='STOP_MARKET',
                        stopPrice=sl,
                        quantity=cantidad_real,
                        reduceOnly=True
                    )
                else:
                    client.futures_create_order(
                        symbol=symbol,
                        side='BUY',
                        type='TAKE_PROFIT_MARKET',
                        stopPrice=tp,
                        quantity=cantidad_real,
                        reduceOnly=True
                    )
                    client.futures_create_order(
                        symbol=symbol,
                        side='BUY',
                        type='STOP_MARKET',
                        stopPrice=sl,
                        quantity=cantidad_real,
                        reduceOnly=True
                    )
            except Exception as e:
                error_msg = f"❌ Error al crear TP/SL: {e}"
                print(error_msg)
                enviar_telegram(error_msg)

            print(f"✅ Orden {senal.upper()} ejecutada correctamente.")
            print(f"🎯 Take Profit: {tp:.4f} | 🛑 Stop Loss: {sl:.4f}")
            enviar_telegram(f"✅ Orden {senal.upper()} ejecutada a {precio_entrada}.\nTP: {tp} | SL: {sl}")
        else:
            error_msg = f"❌ No se pudo ejecutar la orden {senal.upper()}."
            print(error_msg)
            enviar_telegram(error_msg)

    time.sleep(60)  # Esperar antes de la siguiente verificación
