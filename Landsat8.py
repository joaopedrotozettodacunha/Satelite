# Risco de inundação
"""

import ee
import geopandas as gpd
import geemap
from shapely.geometry import Point
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from ipywidgets import HBox, VBox, HTML, VBox as VBoxWidget
from IPython.display import display

# Trigger the authentication flow.
ee.Authenticate() #force=True)

# Initialize the library.
ee.Initialize(project='sentinel-479800')

# Define a coordenada de interesse (longitude, latitude)
lon = -41.31 # Longitude
lat = -21.75  # Latitude
cidade_uf = 'Região Norte Fluminense RJ'

# Define a data de referência e o intervalo de dias
reference_date = '2015-01-20'  # Data de referência
dias_anteriores = 10  # Número de dias antes da data de referência
dias_posteriores = 10  # Número de dias depois da data de referência

# Definir o buffer em graus
buffer_degrees = 0.1  # 5 km em graus

ponto = Point(lon, lat)
poligono_buffer = ponto.buffer(buffer_degrees)
area_interesse = gpd.GeoDataFrame([{'id': 0, 'geometry': poligono_buffer}], crs='EPSG:4326')
print(area_interesse)

ref_date = datetime.strptime(reference_date, '%Y-%m-%d')
start_date = (ref_date - timedelta(days=dias_anteriores)).strftime('%Y-%m-%d')
end_date = (ref_date + timedelta(days=dias_posteriores)).strftime('%Y-%m-%d')

print(f"Data de referência: {reference_date}")
print(f"Período de análise: {start_date} a {end_date}")

geometry_geosjon = area_interesse.iloc[0].geometry
bounds = geometry_geosjon.bounds  # Retorna (minx, miny, maxx, maxy)
minx, miny, maxx, maxy = bounds
geometry = ee.Geometry.Rectangle([minx, miny, maxx, maxy])
print(f"Bounds do buffer: minx={minx:.6f}, miny={miny:.6f}, maxx={maxx:.6f}, maxy={maxy:.6f}")
print(f"Geometria criada como retângulo (box)")

# Função para calcular automaticamente os valores de min/max para visualização RGB
def calculate_rgb_vis_params(image, bands=['B4', 'B3', 'B2'], percentile_min=5, percentile_max=95):
    """
    Calcula automaticamente os parâmetros de visualização RGB baseado em percentis.

    Parâmetros:
    - image: Imagem do Earth Engine
    - bands: Lista de bandas para RGB (padrão: ['B4', 'B3', 'B2'] para Sentinel-2)
    - percentile_min: Percentil mínimo para stretching (padrão: 2)
    - percentile_max: Percentil máximo para stretching (padrão: 98)

    Retorna:
    - Dicionário com parâmetros de visualização
    """
    # Calcula os percentis para cada banda
    percentiles = image.select(bands).reduceRegion(
        reducer=ee.Reducer.percentile([percentile_min, percentile_max]),
        geometry=geometry,
        scale=10,  # Escala de amostragem (ajustar conforme necessário)
        maxPixels=1e9
    ).getInfo()

    # Extrai os valores de min e max para cada banda
    vis_params = {}
    for i, band in enumerate(bands):
        min_key = f'{band}_p{percentile_min}'
        max_key = f'{band}_p{percentile_max}'

        if min_key in percentiles and max_key in percentiles:
            vis_params[f'min_{i}'] = percentiles[min_key]
            vis_params[f'max_{i}'] = percentiles[max_key]
        else:
            # Valores padrão caso não consiga calcular
            vis_params[f'min_{i}'] = 0
            vis_params[f'max_{i}'] = 3000

    # Retorna no formato esperado pelo visualize
    return {
        'min': [vis_params.get('min_0', 0), vis_params.get('min_1', 0), vis_params.get('min_2', 0)],
        'max': [vis_params.get('max_0', 3000), vis_params.get('max_1', 3000), vis_params.get('max_2', 3000)]
    }

### Análise com LANDSAT/LC08/C02/T1_L2

sensor_name = "LANDSAT/LC08/C02/T1_L2"

# Calcula data de base ( da data de referência)
ref_date = datetime.strptime(reference_date, '%Y-%m-%d')
base_date = ref_date - relativedelta(months=3)
base_start_date = (base_date - timedelta(days=15)).strftime('%Y-%m-%d')
base_end_date = (base_date + timedelta(days=15)).strftime('%Y-%m-%d')
print(f"Data de base: {base_date.strftime('%Y-%m-%d')}")
print(f"Período de busca da imagem de base: {base_start_date} a {base_end_date}")

# Filtra a coleção Landsat 5 Collection 2 Level 2
landsat5_collection = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2') \
    .filterBounds(geometry) \
    .filterDate(start_date, end_date)

# Verifica quantas imagens existem
image_count = landsat5_collection.size().getInfo()
print(f"Número de imagens encontradas: {image_count}")

if image_count == 0:
    print("Nenhuma imagem encontrada para o período especificado.")
else:
    # Função para calcular MNDWI para Landsat 5
    # Landsat 5: SR_B2 (verde) e SR_B5 (SWIR)
    def calculate_mndwi_landsat5(image):
        mndwi = image.normalizedDifference(['SR_B2', 'SR_B5']).rename('MNDWI')
        return image.addBands(mndwi)

    # Aplica MNDWI a todas as imagens
    mndwi_collection = landsat5_collection.map(calculate_mndwi_landsat5)

    # Obtém informações das datas das imagens
    def get_image_info(image):
        return ee.Feature(None, {
            'date': image.date().format('YYYY-MM-dd'),
            'system:index': image.get('system:index')
        })

    image_info = mndwi_collection.map(get_image_info)
    dates_list = image_info.aggregate_array('date').getInfo()
    indices_list = image_info.aggregate_array('system:index').getInfo()

    # Remove duplicatas mantendo a ordem
    unique_dates = []
    seen = set()
    for date, idx in zip(dates_list, indices_list):
        if date not in seen:
            unique_dates.append((date, idx))
            seen.add(date)

    print(f"Datas únicas encontradas: {[d[0] for d in unique_dates]}")

    # Função para gerar nome de arquivo
    def generate_filename(cidade_uf, lon, lat, date, sensor):
        """
        Gera nome de arquivo com: cidade_uf_lon_lat_data_sensor
        """
        # Remove espaços e caracteres especiais de cidade_uf
        cidade_uf_clean = cidade_uf.replace(' ', '_').replace('/', '_')
        # Formata coordenadas (mantém sinal negativo como 'N' ou 'S' e 'E' ou 'W')
        lon_str = f"{abs(lon):.4f}".replace('.', 'p')
        lat_str = f"{abs(lat):.4f}".replace('.', 'p')
        lon_dir = 'W' if lon < 0 else 'E'
        lat_dir = 'S' if lat < 0 else 'N'
        lon_formatted = f"{lon_dir}{lon_str}"
        lat_formatted = f"{lat_dir}{lat_str}"
        # Remove barras do nome do sensor
        sensor_clean = sensor.replace('/', '_')
        # Formata data (remove hífens)
        date_clean = date.replace('-', '')

        filename = f"{cidade_uf_clean}_{lon_formatted}_{lat_formatted}_{date_clean}_{sensor_clean}"
        return filename

    # Função para calcular parâmetros de visualização RGB para Landsat 5
    # Landsat 5 Collection 2: SR_B3 (vermelho), SR_B2 (verde), SR_B1 (azul)
    def calculate_rgb_vis_params_landsat5(image, bands=['SR_B3', 'SR_B2', 'SR_B1'], percentile_min=2, percentile_max=98):
        """
        Calcula automaticamente os parâmetros de visualização RGB para Landsat 5.
        Escala: 30m (resolução do Landsat 5)
        """
        # Calcula os percentis para cada banda
        percentiles = image.select(bands).reduceRegion(
            reducer=ee.Reducer.percentile([percentile_min, percentile_max]),
            geometry=geometry,
            scale=30,  # Escala de 30m para Landsat 5
            maxPixels=1e9
        ).getInfo()

        # Extrai os valores de min e max para cada banda
        vis_params = {}
        for i, band in enumerate(bands):
            min_key = f'{band}_p{percentile_min}'
            max_key = f'{band}_p{percentile_max}'

            if min_key in percentiles and max_key in percentiles:
                vis_params[f'min_{i}'] = percentiles[min_key]
                vis_params[f'max_{i}'] = percentiles[max_key]
            else:
                # Valores padrão caso não consiga calcular
                vis_params[f'min_{i}'] = 0
                vis_params[f'max_{i}'] = 10000

        # Retorna no formato esperado pelo visualize
        return {
            'min': [vis_params.get('min_0', 0), vis_params.get('min_1', 0), vis_params.get('min_2', 0)],
            'max': [vis_params.get('max_0', 10000), vis_params.get('max_1', 10000), vis_params.get('max_2', 10000)]
        }

    # Gera e imprime nomes de arquivo para cada data
    print("\nNomes de arquivo gerados:")
    filenames = {}
    for date, idx in unique_dates:
        filename = generate_filename(cidade_uf, lon, lat, date, sensor_name)
        filenames[date] = filename
        print(f"  {date}: {filename}")

    # Busca e processa imagem de base
    print(f"\n=== Processando imagem de base  ===")
    base_collection = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2') \
        .filterBounds(geometry) \
        .filterDate(base_start_date, base_end_date)

    base_count = base_collection.size().getInfo()
    print(f"Imagens encontradas para período de base: {base_count}")

    # Cria mapas individuais para cada imagem
    maps_list = []

    # Processa imagem de base se encontrada
    if base_count > 0:
        base_mndwi_collection = base_collection.map(calculate_mndwi_landsat5)

        # Busca a imagem mais próxima da data de base
        if base_count > 1:
            base_image = base_mndwi_collection.mosaic().clip(geometry)
            base_date_str = base_date.strftime('%Y-%m-%d')
        else:
            base_image = base_mndwi_collection.first().clip(geometry)
            # Obtém a data real da imagem
            base_info = base_mndwi_collection.first().date().format('YYYY-MM-dd').getInfo()
            base_date_str = base_info

        print(f"  Imagem de base processada: {base_date_str}")

        # Calcula parâmetros de visualização automaticamente
        try:
            base_vis_params = calculate_rgb_vis_params_landsat5(base_image, bands=['SR_B3', 'SR_B2', 'SR_B1'])
        except:
            base_vis_params = {'min': [0, 0, 0], 'max': [10000, 10000, 10000]}

        # Cria composição RGB (Landsat 5: SR_B3, SR_B2, SR_B1)
        base_rgb_image = base_image.select(['SR_B3', 'SR_B2', 'SR_B1']).visualize(**base_vis_params)

        # Calcula áreas inundadas (MNDWI > 0.0)
        base_water_threshold = base_image.select('MNDWI').gt(0.0)
        base_flooded_area = base_water_threshold.selfMask().visualize(**{
            'palette': 'red',
            'min': 0,
            'max': 1
        })

        # Cria mapa da imagem de base
        base_map = geemap.Map(
            toolbar_control=False,
            draw_control=False,
            measure_control=False,
            fullscreen_control=False,
            attribution_control=False
        )

        base_map.addLayer(geometry, {'color': 'blue', 'fillColor': '00000000', 'weight': 2}, 'Área de interesse')
        base_map.addLayer(base_rgb_image, {}, 'RGB')
        base_map.addLayer(base_flooded_area, {}, 'Áreas inundadas')
        base_map.centerObject(geometry, 12)
        base_map.addLayerControl()

        # Gera nome de arquivo para imagem de base
        base_filename = generate_filename(cidade_uf, lon, lat, base_date_str, sensor_name)

        # Adiciona imagem de base no início da lista
        maps_list.append({
            'map': base_map,
            'date': f"{base_date_str} (Base)",
            'filename': base_filename
        })
        print(f"  Imagem de base adicionada ao primeiro painel")
    else:
        print(f"  Aviso: Nenhuma imagem encontrada para o período de base")

    for date, idx in unique_dates:
        # Filtra TODAS as imagens da data específica (não apenas por system:index)
        date_start = f"{date}T00:00:00"
        date_end = f"{date}T23:59:59"
        date_collection = mndwi_collection.filterDate(date_start, date_end)

        # Verifica quantas cenas existem para esta data
        scene_count = date_collection.size().getInfo()
        print(f"  Data {date}: {scene_count} cena(s) encontrada(s)")

        # Processa as imagens baseado no número de cenas
        if scene_count > 1:
            # Múltiplas cenas: faz mosaico para combinar todas
            image = date_collection.mosaic()#.clip(geometry)
        elif scene_count == 1:
            # Uma única cena: usa ela diretamente
            image = date_collection.first()#.clip(geometry)
        else:
            print(f"  Aviso: Nenhuma cena encontrada para {date}, pulando...")
            continue

        # Calcula parâmetros de visualização automaticamente
        try:
            vis_params = calculate_rgb_vis_params_landsat5(image, bands=['SR_B3', 'SR_B2', 'SR_B1'])
        except:
            # Fallback para valores padrão se o cálculo falhar
            vis_params = {'min': [0, 0, 0], 'max': [10000, 10000, 10000]}

        # Cria composição RGB (Landsat 5: SR_B3, SR_B2, SR_B1)
        rgb_image = image.select(['SR_B3', 'SR_B2', 'SR_B1']).visualize(**vis_params)

        # Calcula áreas inundadas (MNDWI > 0.0)
        water_threshold = image.select('MNDWI').gt(0.0)
        flooded_area = water_threshold.selfMask().visualize(**{
            'palette': 'red',
            'min': 0,
            'max': 1
        })

        # Cria mapa individual com configurações limpas
        Map = geemap.Map(
            toolbar_control=False,  # Remove toolbar
            draw_control=False,     # Remove controles de desenho
            measure_control=False,   # Remove controles de medida
            fullscreen_control=False, # Remove controle de tela cheia
            attribution_control=False # Remove créditos do ipyleaflet
        )

        Map.addLayer(geometry, {'color': 'blue', 'fillColor': '00000000', 'weight': 2}, 'Área de interesse')
        Map.addLayer(rgb_image, {}, 'RGB')
        Map.addLayer(flooded_area, {}, 'Áreas inundadas')
        Map.centerObject(geometry, 12)

        # Adiciona controle de layers (para habilitar/desabilitar)
        Map.addLayerControl()

        # Armazena mapa, data e nome do arquivo juntos
        maps_list.append({
            'map': Map,
            'date': date,
            'filename': filenames[date]
        })

    # Exibe informações
    print(f"\nSensor: {sensor_name}")
    print(f"Período: {start_date} a {end_date}")
    total_images = len(maps_list)
    print(f"Total de imagens processadas: {total_images} ({'1 imagem de base + ' if base_count > 0 else ''}{len(unique_dates)} do período de análise)")

    # Exibe mapas lado a lado em painéis múltiplos (máximo 2 por linha)
    if len(maps_list) == 1:
        # Se houver apenas um mapa
        map_item = maps_list[0]
        map_item['map'].layout.width = '100%'
        map_item['map'].layout.height = '700px'
        map_item['map'].layout.margin = '0px'
        map_item['map'].layout.padding = '0px'
        map_item['map'].layout.border = 'none'

        # Cria label acima do mapa
        label_html = HTML(f'<div style="display: flex; justify-content: space-between; padding: 8px 12px; background-color: #f5f5f5; border-bottom: 1px solid #ddd; font-weight: bold; font-size: 13px;"><span>{cidade_uf} - {sensor_name}</span><span>{map_item["date"]}</span></div>')
        label_html.layout.width = '100%'
        label_html.layout.margin = '0px'
        label_html.layout.padding = '0px'
        label_html.layout.border = 'none'

        container = VBoxWidget([label_html, map_item['map']])
        container.layout.width = '100%'
        container.layout.margin = '0px'
        container.layout.padding = '0px'
        container.layout.border = 'none'
        display(container)
    else:
        # Configura o tamanho dos mapas para exibição lado a lado (máximo 2 por linha)
        num_maps = len(maps_list)
        width_per_map = '50%'  # Sempre 50% quando há 2 mapas por linha
        height = '700px'

        # Organiza em linhas de 2 mapas
        rows = []
        for i in range(0, num_maps, 2):
            row_items = maps_list[i:i+2]
            row_widgets = []

            for item in row_items:
                item['map'].layout.width = '100%'  # 100% dentro do container
                item['map'].layout.height = height
                item['map'].layout.margin = '0px'
                item['map'].layout.padding = '0px'
                item['map'].layout.border = 'none'

                # Cria label acima do mapa
                label_html = HTML(f'<div style="display: flex; justify-content: space-between; padding: 8px 12px; background-color: #f5f5f5; border-bottom: 1px solid #ddd; font-weight: bold; font-size: 13px;"><span>{cidade_uf} - {sensor_name}</span><span>{item["date"]}</span></div>')
                label_html.layout.width = '100%'
                label_html.layout.margin = '0px'
                label_html.layout.padding = '0px'
                label_html.layout.border = 'none'

                # Cria container vertical com label e mapa
                map_container = VBoxWidget([label_html, item['map']])
                map_container.layout.width = width_per_map
                map_container.layout.height = 'auto'
                map_container.layout.margin = '0px'
                map_container.layout.padding = '0px'
                map_container.layout.border = 'none'
                row_widgets.append(map_container)

            # Se houver apenas 1 item na última linha, ajusta largura
            if len(row_widgets) == 1:
                row_widgets[0].layout.width = '50%'

            # Cria HBox sem espaçamento
            row_box = HBox(row_widgets)
            row_box.layout.width = '100%'
            row_box.layout.height = 'auto'
            row_box.layout.margin = '0px'
            row_box.layout.padding = '0px'
            row_box.layout.border = 'none'
            rows.append(row_box)

        # Cria VBox final sem espaçamento
        final_box = VBox(rows)
        final_box.layout.width = '100%'
        final_box.layout.height = 'auto'
        final_box.layout.margin = '0px'
        final_box.layout.padding = '0px'
        final_box.layout.border = 'none'
        display(final_box)

# Exportar a imagem RGB do período de inundação
task1 = ee.batch.Export.image.toDrive(
    image=rgb_image,                     # A imagem que você quer exportar
    description='RGB_inundacao',         # Nome do arquivo exportado
    fileFormat='GeoTIFF',                # Formato de arquivo
    region=geometry,                     # Define a região de exportação (pode ser a geometria de interesse)
    scale=10,                            # Define a escala em metros por pixel
    maxPixels=1e9                        # Define o número máximo de pixels
)

# Exportar a imagem de áreas inundadas
task2 = ee.batch.Export.image.toDrive(
    image=flooded_area,                  # A imagem que você quer exportar
    description='areas_inundadas',       # Nome do arquivo exportado
    fileFormat='GeoTIFF',                # Formato de arquivo
    region=geometry,                     # Define a região de exportação
    scale=10,                            # Escala em metros por pixel
    maxPixels=1e9                        # Define o número máximo de pixels
)

# task1.start()
# task2.start()
