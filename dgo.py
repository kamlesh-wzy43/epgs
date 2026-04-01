import datetime
import gzip
import xml.etree.ElementTree as ET
import requests

BASE_EPG_URL = "https://storefront.dishhomego.com.np/dhome/android-tv/epg"
BASE_RAILS_URL = "https://storefront.dishhomego.com.np/dhome/android-tv/view/live-tv"
BASE_API_URL = "https://storefront.dishhomego.com.np/dhome/android-tv/"
ASSETS_URL = "https://assets.dishhomego.com.np/"
HEADERS = {
    "Accept-Encoding": "gzip",
    "User-Agent": "okhttp/4.11.0"
}

def indent(elem, level=0):
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for child in elem:
            indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

def build_live_tv_map():
    print("Mapping Live TV Data...")
    json_map = {}
    rails_page = 1
    
    while True:
        try:
            r = requests.get(f"{BASE_RAILS_URL}?page={rails_page}&lang=ENG", headers=HEADERS, timeout=15)
            data = r.json()
            rail_list = data.get("rails", {}).get("list", [])
            if not rail_list:
                break

            for rail in rail_list:
                api_path = rail.get("apiPath")
                if not api_path:
                    continue
                
                cat_page = 1
                while True:
                    try:
                        rail_r = requests.get(f"{BASE_API_URL}{api_path}?page={cat_page}&lang=ENG", headers=HEADERS, timeout=15)
                        rail_data = rail_r.json()
                        channels_list = rail_data.get("list", [])
                        
                        if not channels_list:
                            break
                            
                        for ch in channels_list:
                            epg_id = str(ch.get("epgId"))
                            if epg_id:
                                json_map[epg_id] = ch
                                
                        cat_page += 1
                    except Exception:
                        break
                        
            rails_page += 1
        except Exception:
            break
            
    print(f"Mapped {len(json_map)} channels.")
    return json_map

# Shift the base search window
today = datetime.date.today()
start_dt = datetime.datetime.combine(today, datetime.time(0, 0, 0))
stop_dt = datetime.datetime.combine(today + datetime.timedelta(days=7), datetime.time(23, 59, 59))
start_time = start_dt.strftime("%Y-%m-%d %H:%M:%S")
stop_time = stop_dt.strftime("%Y-%m-%d %H:%M:%S")
prog_date_val = today.strftime("%Y%m%d")

json_channel_data = build_live_tv_map()

channels, programmes = {}, []
page = 1

while True:
    print(f"Fetching EPG page {page}...")
    params = {
        "start": start_time,
        "stop": stop_time,
        "format": "xml",
        "lang": "ENG",
        "page": page
    }

    try:
        response = requests.get(BASE_EPG_URL, headers=HEADERS, params=params, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        elements = 0
        for child in root:
            if child.tag == "channel":
                ch_id = child.get("id")
                icon_elem = child.find("icon")
                if icon_elem is not None:
                    src = icon_elem.get("src")
                    if src and not src.startswith("http"):
                        icon_elem.set("src", f"{ASSETS_URL}{src}")
                
                channels[ch_id] = child
                elements += 1

            elif child.tag == "programme":
                ch_id = child.get("channel")
                rich_data = json_channel_data.get(ch_id, {})
                
                if ch_id not in channels:
                    fallback_channel = ET.Element("channel", {"id": ch_id})
                    disp_name = ET.SubElement(fallback_channel, "display-name")
                    disp_name.text = rich_data.get("title", f"Channel {ch_id}")
                    
                    icon_path = ""
                    for img in rich_data.get("images", []):
                        if img.get("imgType") == "title":
                            icon_path = img.get("path")
                            break
                    if icon_path:
                        icon_elem = ET.SubElement(fallback_channel, "icon")
                        icon_elem.set("src", icon_path if icon_path.startswith("http") else f"{ASSETS_URL}{icon_path}")
                    
                    channels[ch_id] = fallback_channel

                # --- NEW TIMEZONE OFFSET CORRECTION ---
                # Example input: "20260401120000 +0530"
                raw_start = child.get("start")
                raw_stop = child.get("stop")
                
                if raw_start and raw_stop:
                    try:
                        # Extract the numeric part (first 14 chars)
                        start_ts = datetime.datetime.strptime(raw_start[:14], "%Y%m%d%H%M%S")
                        stop_ts = datetime.datetime.strptime(raw_stop[:14], "%Y%m%d%H%M%S")
                        
                        # Add 15 minutes to shift from +0530 to +0545
                        start_ts += datetime.timedelta(minutes=15)
                        stop_ts += datetime.timedelta(minutes=15)
                        
                        # Re-write back with Nepal's offset string
                        child.set("start", f"{start_ts.strftime('%Y%m%d%H%M%S')} +0545")
                        child.set("stop", f"{stop_ts.strftime('%Y%m%d%H%M%S')} +0545")
                    except Exception:
                        pass # If something weird hits it, fall back to the original API string
                # ----------------------------------------

                child.set("catchup-id", rich_data.get("id", ""))
                title = rich_data.get("title", "Unknown Channel")
                category = ", ".join(rich_data.get("catogory", []))
                genres = ", ".join(rich_data.get("genres", []))
                desc_text = f"Watch {title} available from {category} category. Containing {genres} genres."
                
                desc_elem = ET.SubElement(child, "desc")
                desc_elem.text = desc_text
                
                date_elem = ET.SubElement(child, "date")
                date_elem.text = prog_date_val

                icon_path = ""
                for img in rich_data.get("images", []):
                    if img.get("imgType") == "title" and img.get("ratio") in ["16:9", "2:3"]:
                        icon_path = img.get("path")
                        break
                if not icon_path and rich_data.get("images"):
                    icon_path = rich_data.get("images")[0].get("path")

                if icon_path:
                    if not icon_path.startswith("http"):
                        icon_path = f"{ASSETS_URL}{icon_path}"
                    icon_elem = ET.SubElement(child, "icon")
                    icon_elem.set("src", icon_path)

                sub_elem = ET.SubElement(child, "sub-title")
                sub_elem.text = rich_data.get("fullSynopsis", "")

                programmes.append(child)
                elements += 1

        if elements == 0:
            break
        page += 1
    except Exception as e:
        print(f"Error: {e}")
        break

output_root = ET.Element("tv")
output_root.set("generator-info-name", "actions-user")
output_root.set("generator-info-url", "https://github.com/actions-user")

for ch_id in sorted(channels.keys(), key=lambda x: int(x) if x.isdigit() else 9999):
    output_root.append(channels[ch_id])
    
for prog in programmes:
    output_root.append(prog)

indent(output_root)

xml_bytes = ET.tostring(output_root, encoding="utf-8", xml_declaration=True)

with open("gotv.xml", "wb") as f:
    f.write(xml_bytes)
with gzip.open("gotv.xml.gz", "wb") as f:
    f.write(xml_bytes)

print(f"\nSuccess! Total channels: {len(channels)}, Total programs: {len(programmes)}")