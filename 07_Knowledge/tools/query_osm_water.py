import requests
import time


bbox = "23.702296,113.832099,23.729689,113.862918"

query = f"""
[out:json];
(
  way["waterway"]({bbox});
);
out geom;
"""


servers = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]


headers = {
    "User-Agent": "GPX_Terrain_Lab/1.0"
}


for url in servers:
    print("Trying:", url)

    try:
        response = requests.get(
            url,
            params={"data": query},
            headers=headers,
            timeout=60
        )

        print("Status:", response.status_code)

        if response.status_code == 200:
            data = response.json()

            print(
                "Water features:",
                len(data["elements"])
            )

            break

        else:
            print(response.text[:200])

    except Exception as e:
        print("Error:", e)

    time.sleep(2)

else:
    print("All Overpass servers failed.")
