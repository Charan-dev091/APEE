"""
APEE RAG — Knowledge Base
===========================
Product knowledge for ChromaDB vector store.
"""

PRODUCTS = [
    # Sneakers
    {"id":"nb_9060","text":"New Balance 9060 sneakers lifestyle shoe men women retro dad shoe chunky alpine green","category":"sneakers","brand":"New Balance","typical_min":80,"typical_max":150,"msrp":139},
    {"id":"nb_550","text":"New Balance 550 sneakers basketball lifestyle low top white","category":"sneakers","brand":"New Balance","typical_min":70,"typical_max":130,"msrp":110},
    {"id":"nb_2002r","text":"New Balance 2002R sneakers running lifestyle premium","category":"sneakers","brand":"New Balance","typical_min":100,"typical_max":180,"msrp":150},
    {"id":"air_force_1","text":"Nike Air Force 1 sneakers AF1 white low top classic","category":"sneakers","brand":"Nike","typical_min":80,"typical_max":150,"msrp":110},
    {"id":"jordan_1","text":"Air Jordan 1 retro high OG basketball sneakers","category":"sneakers","brand":"Nike","typical_min":120,"typical_max":300,"msrp":180},
    {"id":"adidas_samba","text":"Adidas Samba OG classic sneakers football indoor","category":"sneakers","brand":"Adidas","typical_min":80,"typical_max":130,"msrp":100},
    {"id":"yeezy_350","text":"Adidas Yeezy Boost 350 V2 sneakers Kanye","category":"sneakers","brand":"Adidas","typical_min":200,"typical_max":400,"msrp":220},
    {"id":"vans_old_skool","text":"Vans Old Skool classic skate shoes low top","category":"sneakers","brand":"Vans","typical_min":50,"typical_max":90,"msrp":70},
    {"id":"converse_chuck","text":"Converse Chuck Taylor All Star classic canvas shoes","category":"sneakers","brand":"Converse","typical_min":45,"typical_max":85,"msrp":60},
    {"id":"asics_gel","text":"Asics Gel-Kayano Gel-Nimbus running shoes performance","category":"sneakers","brand":"Asics","typical_min":100,"typical_max":180,"msrp":160},
    # GPUs
    {"id":"rtx_4090","text":"NVIDIA RTX 4090 GPU graphics card gaming 4K AI","category":"gpu","brand":"NVIDIA","typical_min":1500,"typical_max":2500,"msrp":1599},
    {"id":"rtx_4080","text":"NVIDIA RTX 4080 GPU graphics card gaming high end","category":"gpu","brand":"NVIDIA","typical_min":900,"typical_max":1400,"msrp":1199},
    {"id":"rtx_4070","text":"NVIDIA RTX 4070 GPU graphics card gaming mid range","category":"gpu","brand":"NVIDIA","typical_min":400,"typical_max":650,"msrp":599},
    {"id":"rtx_4060","text":"NVIDIA RTX 4060 GPU graphics card gaming budget","category":"gpu","brand":"NVIDIA","typical_min":250,"typical_max":380,"msrp":299},
    {"id":"rx_7900xtx","text":"AMD Radeon RX 7900 XTX GPU graphics card gaming","category":"gpu","brand":"AMD","typical_min":800,"typical_max":1200,"msrp":999},
    {"id":"rx_7800xt","text":"AMD Radeon RX 7800 XT GPU graphics card mid range","category":"gpu","brand":"AMD","typical_min":400,"typical_max":550,"msrp":499},
    # Laptops
    {"id":"macbook_pro_14","text":"Apple MacBook Pro 14 M3 laptop professional creative","category":"laptop","brand":"Apple","typical_min":1600,"typical_max":2200,"msrp":1999},
    {"id":"macbook_air_15","text":"Apple MacBook Air 15 M3 laptop thin light portable","category":"laptop","brand":"Apple","typical_min":1100,"typical_max":1400,"msrp":1299},
    {"id":"dell_xps_15","text":"Dell XPS 15 laptop premium Windows ultrabook","category":"laptop","brand":"Dell","typical_min":1200,"typical_max":2000,"msrp":1799},
    {"id":"asus_rog","text":"ASUS ROG gaming laptop high performance RTX GPU","category":"laptop","brand":"ASUS","typical_min":1200,"typical_max":2500,"msrp":1799},
    # Phones
    {"id":"iphone_15_pro","text":"Apple iPhone 15 Pro Max smartphone titanium camera","category":"phone","brand":"Apple","typical_min":900,"typical_max":1300,"msrp":1199},
    {"id":"iphone_15","text":"Apple iPhone 15 smartphone iOS","category":"phone","brand":"Apple","typical_min":700,"typical_max":950,"msrp":799},
    {"id":"samsung_s24","text":"Samsung Galaxy S24 Ultra smartphone Android camera AI","category":"phone","brand":"Samsung","typical_min":800,"typical_max":1300,"msrp":1299},
    {"id":"pixel_8","text":"Google Pixel 8 Pro smartphone Android AI camera","category":"phone","brand":"Google","typical_min":600,"typical_max":1000,"msrp":999},
    # Monitors
    {"id":"samsung_odyssey","text":"Samsung Odyssey G7 G9 curved gaming monitor 240Hz","category":"monitor","brand":"Samsung","typical_min":400,"typical_max":900,"msrp":699},
    {"id":"lg_oled","text":"LG OLED monitor 4K gaming professional","category":"monitor","brand":"LG","typical_min":600,"typical_max":1500,"msrp":1099},
    {"id":"dell_ultrasharp","text":"Dell UltraSharp monitor 4K IPS professional","category":"monitor","brand":"Dell","typical_min":300,"typical_max":700,"msrp":499},
    # Keyboards
    {"id":"keychron_q1","text":"Keychron Q1 mechanical keyboard gasket mount custom","category":"keyboard","brand":"Keychron","typical_min":150,"typical_max":250,"msrp":199},
    {"id":"logitech_g915","text":"Logitech G915 wireless mechanical keyboard gaming","category":"keyboard","brand":"Logitech","typical_min":150,"typical_max":280,"msrp":249},
    # Headphones
    {"id":"sony_wh1000xm5","text":"Sony WH-1000XM5 wireless noise canceling headphones","category":"headphones","brand":"Sony","typical_min":250,"typical_max":400,"msrp":399},
    {"id":"airpods_pro","text":"Apple AirPods Pro 2 wireless earbuds noise canceling","category":"headphones","brand":"Apple","typical_min":180,"typical_max":280,"msrp":249},
    {"id":"bose_qc45","text":"Bose QuietComfort 45 wireless noise canceling headphones","category":"headphones","brand":"Bose","typical_min":250,"typical_max":380,"msrp":329},
    # Watches
    {"id":"apple_watch_9","text":"Apple Watch Series 9 smartwatch fitness health","category":"watch","brand":"Apple","typical_min":300,"typical_max":500,"msrp":399},
    {"id":"samsung_galaxy_watch","text":"Samsung Galaxy Watch 6 smartwatch Android fitness","category":"watch","brand":"Samsung","typical_min":200,"typical_max":400,"msrp":299},
    {"id":"garmin_fenix","text":"Garmin Fenix 7 GPS smartwatch outdoor sports","category":"watch","brand":"Garmin","typical_min":500,"typical_max":900,"msrp":799},
    # Stocks
    {"id":"nvda_stock","text":"NVIDIA NVDA stock AI GPU semiconductor technology","category":"stock","brand":"NVIDIA","typical_min":0,"typical_max":0,"msrp":0},
    {"id":"aapl_stock","text":"Apple AAPL stock iPhone Mac technology","category":"stock","brand":"Apple","typical_min":0,"typical_max":0,"msrp":0},
    {"id":"tsla_stock","text":"Tesla TSLA stock electric vehicle EV autonomous","category":"stock","brand":"Tesla","typical_min":0,"typical_max":0,"msrp":0},
    {"id":"btc_crypto","text":"Bitcoin BTC cryptocurrency digital asset","category":"crypto","brand":"Bitcoin","typical_min":0,"typical_max":0,"msrp":0},
    {"id":"eth_crypto","text":"Ethereum ETH cryptocurrency smart contracts DeFi","category":"crypto","brand":"Ethereum","typical_min":0,"typical_max":0,"msrp":0},
]
