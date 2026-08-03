import json
import urllib.request
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
# Membenarkan Frontend berhubung dengan Backend Flask
CORS(app)

# --- DEFAULT CONFIG & TARIFF DATA ---
DEFAULT_ENERGY_RATE = 0.2703  # RM / kWh
DEFAULT_NETWORK_RATE = 0.1285  # RM / kWh
DEFAULT_CAPACITY_RATE = 0.0455  # RM / kWh
DEFAULT_AFA_RATE = 0.0380  # RM / kWh
DEFAULT_EFFICIENT_REBATE = (
    0.2100  # RM / kWh (Default Rebat Cekap Tenaga jika <= 600 kWh)
)

RETAIL_CHARGE_FEE = 10.0  # RM (Caj jika > 600 kWh)
SERVICE_TAX_RATE = 0.08  # 8% Cukai Perkhidmatan (Service Tax jika > 600 kWh)

# Koordinat Bandar-Bandar Utama di Seluruh Malaysia
CITY_COORDINATES = {
    'AUTO': None,  # Gunakan IP-based location
    'Alor Setar, Kedah': (6.1248, 100.3678),
    'Ampang Jaya, Selangor': (3.1499, 101.7600),
    'Bintulu, Sarawak': (3.1667, 113.0333),
    'George Town, Pulau Pinang': (5.4164, 100.3327),
    'Ipoh, Perak': (4.5975, 101.0901),
    'Iskandar Puteri, Johor': (1.4230, 103.6578),
    'Johor Bahru, Johor': (1.4927, 103.7414),
    'Kangar, Perlis': (6.4414, 100.1986),
    'Klang, Selangor': (3.0449, 101.4456),
    'Kluang, Johor': (2.0302, 103.3183),
    'Kota Bharu, Kelantan': (6.1256, 102.2381),
    'Kota Kinabalu, Sabah': (5.9804, 116.0735),
    'Kuala Terengganu, Terengganu': (5.3302, 103.1408),
    'Kuala Lumpur': (3.1390, 101.6869),
    'Kuantan, Pahang': (3.8077, 103.3260),
    'Kuching, Sarawak': (1.5533, 110.3592),
    'Kulim, Kedah': (5.3649, 100.5618),
    'Labuan (W.P.)': (5.2831, 115.2308),
    'Melaka Bandaraya Bersejarah': (2.1896, 102.2501),
    'Miri, Sarawak': (4.3995, 113.9914),
    'Muar, Johor': (2.0442, 102.5689),
    'Petaling Jaya, Selangor': (3.1073, 101.6067),
    'Putrajaya (W.P.)': (2.9264, 101.6964),
    'Sandakan, Sabah': (5.8402, 118.1179),
    'Seberang Perai, Pulau Pinang': (5.3732, 100.4023),
    'Seremban, Negeri Sembilan': (2.7258, 101.9424),
    'Shah Alam, Selangor': (3.0738, 101.5183),
    'Sibu, Sarawak': (2.3000, 111.8167),
    'Subang Jaya, Selangor': (3.0567, 101.5851),
    'Tawau, Sabah': (4.2447, 117.8912),
}


def get_current_location():
  """Mengesan lokasi semasa berdasarkan IP."""
  try:
    url = 'http://ip-api.com/json/'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=5) as response:
      data = json.loads(response.read().decode('utf-8'))
      if data.get('status') == 'success':
        lat = data.get('lat')
        lon = data.get('lon')
        city = data.get('city', 'Lokasi Semasa')
        region = data.get('regionName', '')
        location_name = f'{city}, {region} (Lokasi Semasa)'
        return lat, lon, location_name
  except Exception:
    pass
  return 3.1390, 101.6869, 'Kuala Lumpur (Fallback)'


def calculate_tnb_bill(kwh, e_rate, n_rate, c_rate, afa_rate, rebate_rate):
  """Mengira bil elektrik berdasarkan kadar dasar, AFA, rebat, caj peruncitan, dan Service Tax (8%)."""
  energy_charge = kwh * e_rate
  network_charge = kwh * n_rate
  capacity_charge = kwh * c_rate

  gross_bill = energy_charge + network_charge + capacity_charge

  retail_fee = 0.0
  afa_charge = 0.0
  rebate = 0.0
  service_tax = 0.0

  if kwh > 600:
    retail_fee = RETAIL_CHARGE_FEE
    afa_charge = kwh * afa_rate
    subtotal = gross_bill + retail_fee + afa_charge
    service_tax = subtotal * SERVICE_TAX_RATE
  else:
    rebate = kwh * rebate_rate

  net_bill = max(
      0.0, gross_bill - rebate + retail_fee + afa_charge + service_tax
  )

  return (
      net_bill,
      gross_bill,
      rebate,
      retail_fee,
      afa_charge,
      service_tax,
      energy_charge,
      network_charge,
      capacity_charge,
  )


def fetch_weather_psh(lat, lon):
  """Mengambil data ramalan cuaca & radiasi matahari dari Open-Meteo API."""
  try:
    url = f'https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=shortwave_radiation_sum&timezone=Asia%2FKuala_Lumpur'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=5) as response:
      data = json.loads(response.read().decode('utf-8'))

    daily_radiation = data['daily']['shortwave_radiation_sum']
    psh_list = [rad * 0.277778 for rad in daily_radiation if rad is not None]
    avg_psh = sum(psh_list) / len(psh_list) if psh_list else 3.8
    return avg_psh
  except Exception:
    return 3.8


@app.route('/api/cities', methods=['GET'])
def get_cities():
  """API Endpoint untuk memulangkan senarai bandar bagi drop down menu."""
  cities_list = list(CITY_COORDINATES.keys())
  return jsonify({'cities': cities_list})


@app.route('/api/calculate', methods=['POST'])
def calculate():
  """API Endpoint utama pengiraan penjimatan solar."""
  try:
    data = request.get_json()

    kwh = float(data.get('kwh', 0))
    if kwh <= 0:
      return jsonify({'error': 'Nilai kWh tidak sah'}), 400

    selected_city_option = data.get('cityOption', 'AUTO')

    # Kadar Tarif Custom
    custom_rates = data.get('customRates', {})
    e_rate = float(custom_rates.get('eRate', DEFAULT_ENERGY_RATE))
    n_rate = float(custom_rates.get('nRate', DEFAULT_NETWORK_RATE))
    c_rate = float(custom_rates.get('cRate', DEFAULT_CAPACITY_RATE))
    afa_rate = float(custom_rates.get('afaRate', DEFAULT_AFA_RATE))
    rebate_rate = float(
        custom_rates.get('rebateRate', DEFAULT_EFFICIENT_REBATE)
    )

    # Lokasi & Data PSH
    if (
        selected_city_option == 'AUTO'
        or CITY_COORDINATES.get(selected_city_option) is None
    ):
      lat, lon, display_city_name = get_current_location()
    else:
      lat, lon = CITY_COORDINATES[selected_city_option]
      display_city_name = selected_city_option

    avg_psh = fetch_weather_psh(lat, lon)

    # Logik Solar
    daily_kwh = kwh / 30.0
    daytime_kwh = daily_kwh * 0.80  # 80% penggunaan waktu siang
    system_efficiency = 0.80

    recommended_kwp = daytime_kwh / (avg_psh * system_efficiency)

    is_capped = False
    if recommended_kwp > 4.0:
      recommended_kwp = 4.0
      is_capped = True
    elif recommended_kwp < 1.0:
      recommended_kwp = 1.0

    recommended_kwp = round(recommended_kwp, 1)
    monthly_generation_kwh = (
        recommended_kwp * avg_psh * system_efficiency * 30.0
    )
    new_grid_kwh = max(0.0, kwh - monthly_generation_kwh)

    # Pengiraan Bil Asal & Bil Baharu
    (
        orig_net,
        orig_gross,
        orig_rebate,
        orig_retail,
        orig_afa,
        orig_st,
        orig_e,
        orig_n,
        orig_c,
    ) = calculate_tnb_bill(
        kwh, e_rate, n_rate, c_rate, afa_rate, rebate_rate
    )

    (
        new_net,
        new_gross,
        new_rebate,
        new_retail,
        new_afa,
        new_st,
        new_e,
        new_n,
        new_c,
    ) = calculate_tnb_bill(
        new_grid_kwh, e_rate, n_rate, c_rate, afa_rate, rebate_rate
    )

    savings_rm = orig_net - new_net
    savings_pct = (savings_rm / orig_net * 100) if orig_net > 0 else 0

    estimated_cost = recommended_kwp * 4000
    payback_years = (
        (estimated_cost / (savings_rm * 12)) if savings_rm > 0 else 0
    )

    return jsonify({
        'city': display_city_name,
        'lat': round(lat, 4),
        'lon': round(lon, 4),
        'avgPsh': round(avg_psh, 2),
        'monthlyKwh': kwh,
        'recommendedKwp': recommended_kwp,
        'isCapped': is_capped,
        'monthlyGenKwh': round(monthly_generation_kwh, 1),
        'newGridKwh': round(new_grid_kwh, 1),
        # Detail Bil Asal
        'origGross': round(orig_gross, 2),
        'origE': round(orig_e, 2),
        'origN': round(orig_n, 2),
        'origC': round(orig_c, 2),
        'origRebate': round(orig_rebate, 2),
        'origRetail': round(orig_retail, 2),
        'origAfa': round(orig_afa, 2),
        'origSt': round(orig_st, 2),
        'origNet': round(orig_net, 2),
        # Detail Bil Baharu
        'newNet': round(new_net, 2),
        'newRebate': round(new_rebate, 2),
        'newRetail': round(new_retail, 2),
        'newAfa': round(new_afa, 2),
        'newSt': round(new_st, 2),
        # ROI & Penjimatan
        'savingsRm': round(savings_rm, 2),
        'savingsPct': round(savings_pct, 1),
        'estimatedCost': round(estimated_cost, 0),
        'paybackYears': round(payback_years, 1),
        'totalRateUsed': round(e_rate + n_rate + c_rate, 4),
        'rebateRateUsed': rebate_rate,
    })

  except Exception as e:
    return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
  print('🚀 Python Backend Server berjalan di http://127.0.0.1:5000')
  app.run(debug=True, port=5000)