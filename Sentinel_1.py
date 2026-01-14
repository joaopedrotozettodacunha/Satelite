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
lon =  -41.948 # Longitude
lat =  -18.851 # Latitude
cidade_uf = 'Governador Valadares MG'

# Define a data de referência e o intervalo de dias
reference_date = '2022-01-13'  # Data de referência
dias_anteriores = 25  # Número de dias antes da data de referência
dias_posteriores = 25 # Número de dias depois da data de referência

# Definir o buffer em graus
buffer_degrees = 0.1  # 10 km em graus

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

# Função para calcular automaticamente os valores de min/max para visualização RGB para o sentinel 2

"""### Análise com COPERNICUS/S1_GRD"""

def mask_border_noise(image):
          edge = image.lt(-35)
          return image.updateMask(edge.Not())


sensor_name = "COPERNICUS/S1_GRD"

# Calcula o ano anterior à data de referência para imagem de base
ref_date = datetime.strptime(reference_date, '%Y-%m-%d')
previous_year = ref_date.year - 1
base_start_date = f"{previous_year}-01-01"
base_end_date = f"{previous_year}-12-31"
print(f"Ano de referência para imagem de base: {previous_year}")
print(f"Período de busca da imagem de base: {base_start_date} a {base_end_date}")

# Filtra a coleção Sentinel-2 Surface Reflectance Harmonized
s1_collection = (
    ee.ImageCollection('COPERNICUS/S1_GRD')
    .filterBounds(geometry)
    .filterDate(start_date, end_date)
    .filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING'))
    .filter(ee.Filter.eq('resolution_meters', 10))
    .filter(ee.Filter.eq('instrumentMode', 'IW'))
    .filter(ee.Filter.listContains(
        'transmitterReceiverPolarisation', 'VV'))
    .select('VV')
    .map(mask_border_noise)
)


# Verifica quantas imagens existem
image_count = s1_collection.size().getInfo()
print(f"Número de imagens encontradas: {image_count}")

if image_count == 0:
    print("Nenhuma imagem encontrada para o período especificado.")
else:
    # Função para calcular
    def calculate_flood_s1(image):
      vv = image.select('VV')
      flooded = vv.lt(-17).rename('FLOOD')  # limiar típico
      return image.addBands(flooded)

    # Aplica  a todas as imagens
    flood_collection = s1_collection.map(calculate_flood_s1)

    # Obtém informações das datas das imagens
    def get_image_info(image):
        return ee.Feature(None, {
            'date': image.date().format('YYYY-MM-dd'),
            'system:index': image.get('system:index')
        })



    image_info = flood_collection.map(get_image_info)

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

    # Gera e imprime nomes de arquivo para cada data
    print("\nNomes de arquivo gerados:")
    filenames = {}
    for date, idx in unique_dates:
        filename = generate_filename(cidade_uf, lon, lat, date, sensor_name)
        filenames[date] = filename
        print(f"  {date}: {filename}")

    # Função para aplicar máscara de nuvens no Sentinel-2


    # Busca e processa imagem de base (mosaico do ano anterior)
    print(f"\n=== Processando imagem de base (mosaico do ano anterior) ===")
    base_collection = (
    ee.ImageCollection('COPERNICUS/S1_GRD')
    .filterBounds(geometry)
    .filterDate(base_start_date, base_end_date)
    .filter(ee.Filter.eq('orbitProperties_pass', 'DESCENDING'))
    .filter(ee.Filter.eq('resolution_meters', 10))
    .filter(ee.Filter.eq('instrumentMode', 'IW'))
    .filter(ee.Filter.listContains(
        'transmitterReceiverPolarisation', 'VV'))
    .select('VV')
    .map(mask_border_noise)
    )



    base_count = base_collection.size().getInfo()
    print(f"Imagens encontradas para período de base (ano {previous_year}): {base_count}")

    # Cria mapas individuais para cada imagem
    maps_list = []

    # Processa imagem de base se encontrada
    if base_count > 0:
        # Aplica máscara de nuvens em todas as imagens
        base_collection_masked = base_collection

        # Calcula a mediana temporal de todas as imagens do ano anterior
        # A mediana é mais robusta que a média para eliminar outliers
        base_image_median = base_collection_masked.median()

        # Calcula  na imagem mediana
        base_image = calculate_flood_s1(base_image_median)

        base_date_str = f"{previous_year} (Mediana anual)"
        print(f"  Imagem de base processada: Composição mediana do ano {previous_year}")
        print(f"  Total de imagens utilizadas: {base_count}")





        # Cria composição RGB
        rgb_image = base_image.visualize(
          bands=['VV'],
          min=-25,
          max=0
        )


        # Calcula áreas inundadas
        base_flooded_area = (
        base_image
        .select('FLOOD')
        .selfMask()
        .visualize(
            bands=['FLOOD'],
            palette=['red']
        )

        )


        # Cria mapa da imagem de base
        base_map = geemap.Map(
            toolbar_control=False,
            draw_control=False,
            measure_control=False,
            fullscreen_control=False,
            attribution_control=False
        )

        base_map.addLayer(geometry, {'color': 'blue', 'fillColor': '00000000', 'weight': 2}, 'Área de interesse')
        base_map.addLayer(rgb_image, {}, 'VV (Radar)')
        base_map.addLayer(base_flooded_area, {}, 'Áreas inundadas')
        base_map.centerObject(geometry, 12)
        base_map.addLayerControl()

        # Gera nome de arquivo para imagem de base (usa o ano como data)
        base_date_for_filename = f"{previous_year}0101"  # Formato YYYYMMDD para o nome do arquivo
        base_filename = generate_filename(cidade_uf, lon, lat, base_date_for_filename, sensor_name)
        # Adiciona sufixo para indicar que é mediana anual
        base_filename = base_filename.replace(f"_{previous_year}0101_", f"_{previous_year}_MEDIANA_")

        # Adiciona imagem de base no início da lista
        maps_list.append({
            'map': base_map,
            'date': f"{base_date_str}",
            'filename': base_filename
        })
        print(f"  Imagem de base adicionada ao primeiro painel")
    else:
        print(f"  Aviso: Nenhuma imagem encontrada para o período de base")

    for date, idx in unique_dates:
        # Filtra TODAS as imagens da data específica (não apenas por system:index)
        date_start = f"{date}T00:00:00"
        date_end = f"{date}T23:59:59"
        date_collection = flood_collection.filterDate(date_start, date_end)

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
        vv_vis = image.visualize(
          bands=['VV'],
          min=-25,
          max=0
        )



        # Cria composição RGB
        vis_params = {'min': -25, 'max': 0}



        flooded_area = image.select('FLOOD').selfMask().visualize(
            bands=['FLOOD'],
            palette=['red']
        )



        # Cria mapa individual com configurações limpas
        Map = geemap.Map(
            toolbar_control=False,  # Remove toolbar
            draw_control=False,     # Remove controles de desenho
            measure_control=False,   # Remove controles de medida
            fullscreen_control=False, # Remove controle de tela cheia
            attribution_control=False # Remove créditos do ipyleaflet
        )
        vv_vis = image.visualize(
          bands=['VV'],
          min=-25,
          max=0
        )

        Map.addLayer(geometry, {'color': 'blue', 'fillColor': '00000000', 'weight': 2}, 'Área de interesse')
        Map.addLayer(vv_vis, {}, 'VV (Radar)')
        Map.addLayer(flooded_area, {}, 'Áreas inundadas')
        Map.centerObject(geometry,12)

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
    if base_count > 0:
        print(f"Total de imagens processadas: {total_images} (1 composição mediana do ano {previous_year} + {len(unique_dates)} do período de análise)")
    else:
        print(f"Total de imagens processadas: {total_images} ({len(unique_dates)} do período de análise)")

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

# task1.start()
# task2.start()
