import pandas as pd
import os

# Obtener la ruta del directorio actual donde está el script
directorio_actual = os.path.dirname(os.path.abspath(__file__))
archivo = os.path.join(directorio_actual, 'registro_operaciones_atom.csv')

# Verificar si el archivo existe
if not os.path.exists(archivo):
    print(f"❌ Error: No se encontró el archivo {archivo}")
    print("📁 Archivos disponibles en el directorio:")
    for archivo_en_dir in os.listdir(directorio_actual):
        if archivo_en_dir.endswith('.csv'):
            print(f"   • {archivo_en_dir}")
    exit(1)

try:
    df = pd.read_csv(archivo)
    print(f"✅ Archivo cargado exitosamente: {archivo}")
    print(f"📊 Total de registros: {len(df)}")
    
    # Mostrar las primeras filas para verificar la estructura
    print("\n📋 Estructura del archivo:")
    print(df.head())
    print(f"\n📋 Columnas disponibles: {list(df.columns)}")
    
except Exception as e:
    print(f"❌ Error al leer el archivo: {e}")
    exit(1)

# Asegúrate de que la columna PnL sea numérica
df['PnL'] = pd.to_numeric(df['PnL'], errors='coerce')

# Operaciones ganadoras: aquellas cuyo resultado fue TP
ganadoras = df[df['Resultado'].str.upper() == 'TP']
# Operaciones perdedoras: aquellas cuyo resultado fue SL
perdedoras = df[df['Resultado'].str.upper() == 'SL']

total = len(df)
num_ganadoras = len(ganadoras)
num_perdedoras = len(perdedoras)
ganancia_neta = df['PnL'].sum()

print(f"\n📈 **RESULTADOS DEL ANÁLISIS**")
print(f"Total de operaciones: {total}")
print(f"Operaciones ganadoras: {num_ganadoras}")
print(f"Operaciones perdedoras: {num_perdedoras}")
print(f"Ganancia neta: {ganancia_neta:.4f} USDT")

if total > 0:
    porcentaje_ganadoras = (num_ganadoras / total) * 100
    print(f"Porcentaje de éxito: {porcentaje_ganadoras:.1f}%")