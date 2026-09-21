import zipfile, xml.etree.ElementTree as ET
K = '{http://www.opengis.net/kml/2.2}'
p = r'C:\Users\tucke\OneDrive\Documents\Claude\Projects\TBDI Modeling\Mireye\TBDI_WS_Combined.kmz'
root = ET.fromstring(zipfile.ZipFile(p).read('doc.kml').decode('utf-8'))

def walk(el, d=0):
    for f in el.findall(K + 'Folder'):
        nm = f.find(K + 'name')
        label = nm.text if nm is not None else '?'
        n = len(f.findall(K + 'Placemark'))
        print('  ' * d + f'- {label:58} placemarks={n}')
        walk(f, d + 1)

walk(root.find(K + 'Document'))
