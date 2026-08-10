import json
import urllib.request
from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime,timedelta

app = Flask(__name__)
# Membenarkan Frontend berhubung dengan Backend Flask
CORS(app)

# --- DEFAULT CONFIG & TARIFF DATA ---
DEFAULT_ENERGY_RATE = 0.2703   # RM / kWh
DEFAULT_NETWORK_RATE = 0.1285  # RM / kWh
DEFAULT_CAPACITY_RATE = 0.0455 # RM / kWh
DEFAULT_AFA_RATE = 0.0380      # RM / kWh
DEFAULT_EFFICIENT_REBATE = 0.2100 # RM / kWh (Default Rebat Cekap Tenaga jika <= 600 kWh)

RETAIL_CHARGE_FEE = 10.0   # RM (Caj jika > 600 kWh)
SERVICE_TAX_RATE = 0.08    # 8% Cukai Perkhidmatan (Service Tax jika > 600 kWh)
KWTBB_RATE = 0.016      # 1.6%

# Koordinat Bandar-Bandar Utama di Seluruh Malaysia
CITY_COORDINATES = {
    'AUTO': None,  # Gunakan GPS browser / Fallback IP
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
    'Kuala Berang, Terengganu': (4.9688, 103.0118),
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


def get_location_name_from_coords(lat, lon):
    """Mendapatkan nama bandar berdasarkan koordinat GPS menggunakan OpenStreetMap."""

    try:

        url = (
            f"https://nominatim.openstreetmap.org/reverse"
            f"?lat={lat}&lon={lon}&format=jsonv2"
        )

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "SolarSavingsCalculator/1.0"
            }
        )

        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))

        address = data.get("address", {})

        city = (
            address.get("city")
            or address.get("town")
            or address.get("municipality")
            or address.get("village")
            or address.get("county")
        )

        state = address.get("state")

        if city and state:
            return f"{city}, {state} (Lokasi GPS Semasa)"

        elif city:
            return f"{city} (Lokasi GPS Semasa)"

    except Exception as e:

        print("Reverse Geocode Error:", e)

    return f"Lokasi GPS ({lat:.2f}°, {lon:.2f}°)"



#calculate spawning month
def calculate_spanning_month_afa(kwh,billing_start,billing_end,afa_rate_1,afa_rate_2):
    """
    Mengira AFA untuk billing period yang merentasi dua bulan secara prorata mengikut bilangan hari.
    """
    # Jika tarikh tidak diberikan, gunakan kadar pertama (afa_rate_1)
    if not billing_start or not billing_end:
        return kwh * afa_rate_1

    try:
        start_date = datetime.strptime(billing_start, "%Y-%m-%d").date()
        end_date = datetime.strptime(billing_end, "%Y-%m-%d").date()
    except ValueError:
        return kwh * afa_rate_1

    if end_date <= start_date:
        return kwh * afa_rate_1

    # Jika dalam bulan dan tahun yang sama
    if start_date.year == end_date.year and start_date.month == end_date.month:
        return kwh * afa_rate_1

    # Pengiraan bilangan hari
    total_days = (end_date - start_date).days

    # Cari hari terakhir untuk bulan pertama
    first_month_end = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    first_month_days = (first_month_end - start_date).days + 1
    second_month_days = total_days - first_month_days

    if total_days <= 0 or first_month_days <= 0 or second_month_days <= 0:
        return kwh * afa_rate_1

    # Agihan kWh mengikut nisbah hari
    first_month_kwh = kwh * (first_month_days / total_days)
    second_month_kwh = kwh * (second_month_days / total_days)

    afa_first = first_month_kwh * afa_rate_1
    afa_second = second_month_kwh * afa_rate_2

    return afa_first + afa_second

def calculate_taxable_afa(kwh,billing_start,billing_end,afa_rate_1,afa_rate_2):
    """
    Mengira bahagian AFA yang berkaitan dengan penggunaan
    melebihi 600 kWh untuk tujuan Service Tax.
    """

    if kwh <= 600:
        return 0.0

    taxable_kwh = kwh - 600

    # Jika tiada spanning month,
    # semua taxable kWh menggunakan rate pertama.
    if not billing_start or not billing_end:
        return taxable_kwh * afa_rate_1

    start_date = datetime.strptime(
        billing_start, "%Y-%m-%d"
    ).date()

    end_date = datetime.strptime(
        billing_end, "%Y-%m-%d"
    ).date()

    if (
        start_date.year == end_date.year
        and start_date.month == end_date.month
    ):
        return taxable_kwh * afa_rate_1

    total_days = (end_date - start_date).days

    first_month_end = (
        start_date.replace(day=28)
        + timedelta(days=4)
    )
    first_month_end = first_month_end.replace(day=1) - timedelta(days=1)

    first_month_days = (
        first_month_end - start_date
    ).days + 1

    second_month_days = total_days - first_month_days

    first_month_kwh = (
        kwh * first_month_days / total_days
    )

    second_month_kwh = (
        kwh * second_month_days / total_days
    )

    # Bahagikan taxable 600+ secara proporsional
    taxable_first = max(
        0.0,
        first_month_kwh - (600 * first_month_days / total_days)
    )

    taxable_second = max(
        0.0,
        second_month_kwh - (600 * second_month_days / total_days)
    )

    return (
        taxable_first * afa_rate_1
        + taxable_second * afa_rate_2
    )
    

#main calculation
def calculate_tnb_bill(kwh,e_rate,n_rate,c_rate,afa_rate_1,afa_rate_2,billing_start,billing_end):
    """Mengira bil elektrik berdasarkan kadar dasar, AFA, rebat, caj peruncitan, Service Tax dan KWTBB."""

    energy_charge = kwh * e_rate
    network_charge = kwh * n_rate
    capacity_charge = kwh * c_rate

    gross_bill = energy_charge + network_charge + capacity_charge

    retail_fee = 0.0
    afa_charge = 0.0
    rebate = 0.0
    service_tax = 0.0
    kwtbb = 0.0

    # ==========================
    # REBAT CEKAP TENAGA
    # ==========================

    rebate_rate = get_efficient_rebate_rate(kwh)
    rebate = kwh * rebate_rate

    # ==========================
    # AFA + SERVICE TAX
    # ==========================

    if kwh > 600:

        retail_fee = RETAIL_CHARGE_FEE

        afa_charge = calculate_spanning_month_afa(
            kwh,
            billing_start,
            billing_end,
            afa_rate_1,
            afa_rate_2
        )

        taxable_kwh = kwh - 600

        taxable_energy = taxable_kwh * e_rate
        taxable_network = taxable_kwh * n_rate
        taxable_capacity = taxable_kwh * c_rate
        taxable_afa = calculate_taxable_afa(
            kwh,
            billing_start,
            billing_end,
            afa_rate_1,
            afa_rate_2
        )

        taxable_subtotal = (
            taxable_energy
            + taxable_network
            + taxable_capacity
            + taxable_afa
            + retail_fee
        )

        service_tax = taxable_subtotal * SERVICE_TAX_RATE

    # ==========================
    # KWTBB
    # ==========================

    kwtbb_base = gross_bill - rebate

    if kwh > 300:
        kwtbb = kwtbb_base * KWTBB_RATE

    # ==========================
    # NET BILL
    # ==========================

    net_bill = max(
        0.0,
        gross_bill
        - rebate
        + retail_fee
        + afa_charge
        + service_tax
        + kwtbb
    )

    return (
        net_bill,
        gross_bill,
        rebate,
        retail_fee,
        afa_charge,
        service_tax,
        kwtbb,
        energy_charge,
        network_charge,
        capacity_charge
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
        custom_lat = data.get('lat') # Menerima lat dari GPS browser jika ada
        custom_lon = data.get('lon') # Menerima lon dari GPS browser jika ada

        # Kadar Tarif Custom
        custom_rates = data.get('customRates', {})

        e_rate = float(
            custom_rates.get('eRate', DEFAULT_ENERGY_RATE)
        )

        n_rate = float(
            custom_rates.get('nRate', DEFAULT_NETWORK_RATE)
        )

        c_rate = float(
            custom_rates.get('cRate', DEFAULT_CAPACITY_RATE)
        )

        afa_rate_1 = float(
            custom_rates.get('afaRate1', 0.0359)
        )

        afa_rate_2 = float(
            custom_rates.get('afaRate2', 0.0380)
        )

        billing_start = data.get('billingStart')
        billing_end = data.get('billingEnd')

        # Logik Penentuan Lokasi (Tepat melalui GPS)
        if custom_lat is not None and custom_lon is not None:
            lat = float(custom_lat)
            lon = float(custom_lon)
            display_city_name = get_location_name_from_coords(lat, lon)
        elif selected_city_option != 'AUTO' and CITY_COORDINATES.get(selected_city_option) is not None:
            lat, lon = CITY_COORDINATES[selected_city_option]
            display_city_name = selected_city_option
        else:
            # Fallback ke Kuala Lumpur jika tiada GPS/pilihan bandar
            lat, lon = 3.1390, 101.6869
            display_city_name = "Kuala Lumpur (Default)"

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
        monthly_generation_kwh = recommended_kwp * avg_psh * system_efficiency * 30.0
        new_grid_kwh = max(0.0, kwh - monthly_generation_kwh)

        # Pengiraan Bil Asal & Bil Baharu
        (
            orig_net,
            orig_gross,
            orig_rebate,
            orig_retail,
            orig_afa,
            orig_st,
            orig_kwtbb,
            orig_e,
            orig_n,
            orig_c,
        ) = calculate_tnb_bill(
            kwh,
            e_rate,
            n_rate,
            c_rate,
            afa_rate_1,
            afa_rate_2,
            billing_start,
            billing_end
        )

 
        (
            new_net,
            new_gross,
            new_rebate,
            new_retail,
            new_afa,
            new_st,
            new_kwtbb,
            new_e,
            new_n,
            new_c,
        ) = calculate_tnb_bill(
            new_grid_kwh,
            e_rate,
            n_rate,
            c_rate,
            afa_rate_1,
            afa_rate_2,
            billing_start,
            billing_end
        )

        savings_rm = orig_net - new_net
        savings_pct = (savings_rm / orig_net * 100) if orig_net > 0 else 0

        estimated_cost = recommended_kwp * 4000
        payback_years = (estimated_cost / (savings_rm * 12)) if savings_rm > 0 else 0

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
            'origKwtbb': round(orig_kwtbb,2),
            'origNet': round(orig_net, 2),
            # Detail Bil Baharu
            'newNet': round(new_net, 2),
            'newRebate': round(new_rebate, 2),
            'newRetail': round(new_retail, 2),
            'newAfa': round(new_afa, 2),
            'newSt': round(new_st, 2),
            'newKwtbb': round(new_kwtbb,2),
            # ROI & Penjimatan
            'savingsRm': round(savings_rm, 2),
            'savingsPct': round(savings_pct, 1),
            'estimatedCost': round(estimated_cost, 0),
            'paybackYears': round(payback_years, 1),
            'totalRateUsed': round(e_rate + n_rate + c_rate, 4),
            'rebateRateUsed': get_efficient_rebate_rate(kwh),
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_efficient_rebate_rate(kwh):

    if kwh <= 200:
        return 0.250
    elif kwh <= 250:
        return 0.245
    elif kwh <= 300:
        return 0.225
    elif kwh <= 350:
        return 0.210
    elif kwh <= 400:
        return 0.170
    elif kwh <= 450:
        return 0.145
    elif kwh <= 500:
        return 0.120
    elif kwh <= 550:
        return 0.105
    elif kwh <= 600:
        return 0.090
    elif kwh <= 650:
        return 0.075
    elif kwh <= 700:
        return 0.055
    elif kwh <= 750:
        return 0.045
    elif kwh <= 800:
        return 0.040
    elif kwh <= 850:
        return 0.025
    elif kwh <= 900:
        return 0.010
    elif kwh <= 1000:
        return 0.005

    return 0.0


if __name__ == '__main__':
    print('🚀 Python Backend Server berjalan di http://127.0.0.1:5000')
    app.run(debug=True, port=5000)