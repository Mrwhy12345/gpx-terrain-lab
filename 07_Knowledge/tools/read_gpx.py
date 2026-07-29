import xml.etree.ElementTree as ET

file = "06_Experiment/S02_ColorTest/input/2025-02-23 从化星溪线.gpx"

tree = ET.parse(file)
root = tree.getroot()

ns = {"gpx": "http://www.topografix.com/GPX/1/1"}

lats = []
lons = []

for p in root.findall(".//gpx:trkpt", ns):
    lats.append(float(p.attrib["lat"]))
    lons.append(float(p.attrib["lon"]))

print("Point count:", len(lats))

print("Latitude:")
print(min(lats), max(lats))

print("Longitude:")
print(min(lons), max(lons))
