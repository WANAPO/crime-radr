from datetime import datetime, timezone
import html
import json
from pathlib import Path
import folium
import requests
from src.db import fetch_all_incidents, init_db

OUTPUT_HTML = Path("output/index.html")
PROVINCES_GEOJSON_PATH = Path("data/sa_provinces.geojson")
PROVINCES_GEOJSON_URL = (
    "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/south-africa.geojson"
)

DRUG_CAR_SVG = """
<svg width="26" height="22" viewBox="0 0 36 28" fill="none" xmlns="http://www.w3.org/2000/svg">
  <!-- Tiny car silhouette -->
  <path d="M5 17L8 10.5C8.5 9.5 9.5 9 10.6 9H18.4C19.5 9 20.5 9.5 21 10.5L24 17H26.5C27.9 17 29 18.1 29 19.5V22H26.8C26.4 20.3 24.9 19 23.1 19C21.3 19 19.8 20.3 19.4 22H12.6C12.2 20.3 10.7 19 8.9 19C7.1 19 5.6 20.3 5.2 22H3V19.5C3 18.1 3.9 17 5 17Z" fill="#ffffff" stroke="#111827" stroke-width="1.3"/>
  <circle cx="8.9" cy="22" r="2.2" fill="#dc2626" stroke="#111827" stroke-width="1.2"/>
  <circle cx="23.1" cy="22" r="2.2" fill="#dc2626" stroke="#111827" stroke-width="1.2"/>
  <!-- Drug capsule badge -->
  <g transform="translate(19, 1) rotate(28)">
    <rect x="0" y="0" width="14" height="7.5" rx="3.75" fill="#ffffff" stroke="#111827" stroke-width="1.2"/>
    <path d="M7 0.6H10.25C12.1 0.6 13.4 2 13.4 3.75C13.4 5.5 12.1 6.9 10.25 6.9H7V0.6Z" fill="#a855f7"/>
  </g>
</svg>
"""

TINY_UBERCARD_SVG = """
<svg width="24" height="22" viewBox="0 0 32 26" fill="none" xmlns="http://www.w3.org/2000/svg">
  <!-- Compact / tiny city car ("Ubercar") -->
  <path d="M7.5 16.5L10.2 8.5C10.6 7.4 11.6 6.8 12.8 6.8H19.2C20.4 6.8 21.4 7.4 21.8 8.5L24.5 16.5H26.2C27.5 16.5 28.5 17.5 28.5 18.8V20.5H26.4C26 18.8 24.5 17.6 22.8 17.6C21.1 17.6 19.6 18.8 19.2 20.5H12.8C12.4 18.8 10.9 17.6 9.2 17.6C7.5 17.6 6 18.8 5.6 20.5H3.5V18.8C3.5 17.5 4.5 16.5 5.8 16.5H7.5Z" fill="#ffffff" stroke="#111827" stroke-width="1.3"/>
  <path d="M11.2 15.5L12.8 9.2H19.2L20.8 15.5H11.2Z" fill="#3f3f46"/>
  <circle cx="9.2" cy="20.5" r="2.2" fill="#f59e0b" stroke="#111827" stroke-width="1.2"/>
  <circle cx="22.8" cy="20.5" r="2.2" fill="#f59e0b" stroke="#111827" stroke-width="1.2"/>
</svg>
"""

CIT_CASH_TRUCK_SVG = """
<svg width="30" height="24" viewBox="0 0 40 28" fill="none" xmlns="http://www.w3.org/2000/svg">
  <!-- Armoured CIT / money truck body -->
  <rect x="11" y="7" width="16" height="13" rx="1.8" fill="#ffffff" stroke="#111827" stroke-width="1.3"/>
  <path d="M27 11H32.5L35.5 15V20H27V11Z" fill="#e4e4e7" stroke="#111827" stroke-width="1.3"/>
  <rect x="28.8" y="12.5" width="4.2" height="3.2" rx="0.6" fill="#3f3f46"/>
  <!-- Cash pouring out from rear -->
  <rect x="2" y="8" width="6.5" height="3.6" rx="0.7" transform="rotate(-18 2 8)" fill="#22c55e" stroke="#111827" stroke-width="1"/>
  <rect x="1" y="13.2" width="6.5" height="3.6" rx="0.7" transform="rotate(14 1 13.2)" fill="#4ade80" stroke="#111827" stroke-width="1"/>
  <rect x="4.5" y="17.5" width="6" height="3.4" rx="0.7" transform="rotate(-10 4.5 17.5)" fill="#16a34a" stroke="#111827" stroke-width="1"/>
  <!-- Wheels -->
  <circle cx="15.5" cy="21" r="2.5" fill="#ef4444" stroke="#111827" stroke-width="1.2"/>
  <circle cx="31.5" cy="21" r="2.5" fill="#ef4444" stroke="#111827" stroke-width="1.2"/>
</svg>
"""

CATEGORY_META = {
    "drug_bust": {
        "label": "Major Drug Busts & Labs",
        "color": "#a855f7",
        "badge_bg": "#dc2626",
        "svg": DRUG_CAR_SVG,
    },
    "hijacking": {
        "label": "Hijackings & Stolen Vehicles",
        "color": "#f59e0b",
        "badge_bg": "#b91c1c",
        "svg": TINY_UBERCARD_SVG,
    },
    "cit_robbery": {
        "label": "CIT Heists & Money Trucks",
        "color": "#ef4444",
        "badge_bg": "#991b1b",
        "svg": CIT_CASH_TRUCK_SVG,
    },
}


def ensure_sa_provinces_geojson() -> dict | None:
    """Download and locally cache South Africa's provincial boundaries GeoJSON."""
    if PROVINCES_GEOJSON_PATH.exists():
        try:
            with open(PROVINCES_GEOJSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    try:
        resp = requests.get(PROVINCES_GEOJSON_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        PROVINCES_GEOJSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(PROVINCES_GEOJSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data
    except Exception as exc:
        print(f"[WARN] Could not fetch SA province boundaries GeoJSON: {exc}")
        return None


def build_popup_html(incident: dict) -> str:
    meta = CATEGORY_META[incident["category"]]
    details = dict(incident.get("details", {}))

    gallery = details.pop("gallery", [])
    if not gallery and incident.get("image_url"):
        gallery = [incident["image_url"]]

    detail_rows = ""
    for k, v in details.items():
        label = html.escape(k.replace("_", " ").upper())
        val_str = str(v).strip() or "N/A"
        val = html.escape(val_str)
        detail_rows += (
            f"<div style='margin:2px 0;'>"
            f"<strong style='color:#ef4444; font-weight:800;'>{label}:</strong> "
            f"<span style='color:#ffffff; font-weight:700;'>{val}</span>"
            f"</div>"
        )

    img_block = ""
    if gallery:
        img_tags = "".join(
            f'<img src="{html.escape(url)}" alt="Incident photo" '
            f'style="width:100%; max-height:135px; object-fit:cover; border-radius:4px; border:1px solid #52525b; margin-bottom:4px;" '
            f'onerror="this.style.display='none';">'
            for url in gallery[:2]
            if url
        )
        if img_tags:
            img_block = f'<div style="margin:6px 0;">{img_tags}</div>'

    return f"""
    <div style="font-family:'Space Grotesk',system-ui,-apple-system,sans-serif; width:265px; color:#ffffff; background:#18181b; border:1px solid #71717a; padding:10px; border-radius:8px;">
        <span style="display:inline-block; background:{meta['badge_bg']}; color:#ffffff; font-size:10px; font-weight:800; padding:2px 8px; border-radius:999px; text-transform:uppercase; letter-spacing:0.04em;">
            {html.escape(meta['label'])}
        </span>
        <h4 style="margin:6px 0 3px 0; font-size:13px; font-weight:800; color:#ffffff; line-height:1.25;">
            {html.escape(incident['title'])}
        </h4>
        <div style="font-size:11px; color:#d4d4d8; font-weight:700; margin-bottom:5px;">
            {html.escape(incident['reported_at'])} &bull; {html.escape(incident.get('province', 'N/A'))}
        </div>
        {img_block}
        <div style="font-size:11px; background:#27272a; border:1px solid #52525b; padding:6px 8px; border-radius:5px; margin:6px 0; color:#ffffff;">
            {detail_rows}
        </div>
        <p style="font-size:11px; line-height:1.35; color:#e4e4e7; font-weight:600; margin:5px 0;">
            {html.escape(incident['summary'])}
        </p>
        <a href="{html.escape(incident['source_url'])}" target="_blank" rel="noopener noreferrer"
           style="display:inline-block; margin-top:4px; font-size:11px; color:#ef4444; text-decoration:none; font-weight:800;">
            VIEW SOURCE POST &rarr;
        </a>
    </div>
    """

def build_custom_marker_icon(category: str) -> folium.DivIcon:
    meta = CATEGORY_META[category]
    border_col = meta["color"]
    svg_markup = meta["svg"]
    return folium.DivIcon(
        html=f"""
        <div style="
            width: 34px;
            height: 30px;
            margin-left: -17px;
            margin-top: -15px;
            background: rgba(24, 24, 27, 0.95);
            border: 2px solid {border_col};
            border-radius: 7px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 3px 10px rgba(0, 0, 0, 0.65);
        ">
            {svg_markup}
        </div>
        """,
        icon_size=(34, 30),
        icon_anchor=(17, 15),
    )


def generate_map() -> Path:
    init_db()
    incidents = fetch_all_incidents()

    sa_map = folium.Map(
        location=[-28.8, 24.8],
        zoom_start=6,
        tiles=None,
        control_scale=True,
    )

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ",
        name="Grey Tactical Base",
        control=False,
    ).add_to(sa_map)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
        attr="Labels &copy; Esri",
        name="Light-Grey Line & Label Overlay",
        overlay=True,
        control=False,
    ).add_to(sa_map)

    provinces_geojson = ensure_sa_provinces_geojson()
    if provinces_geojson:
        folium.GeoJson(
            provinces_geojson,
            name="SA Provincial Boundaries",
            control=False,
            style_function=lambda _: {
                "fillColor": "#52525b",
                "fillOpacity": 0.16,
                "color": "#e4e4e7",
                "weight": 1.6,
                "opacity": 0.92,
            },
            highlight_function=lambda _: {
                "fillColor": "#71717a",
                "fillOpacity": 0.28,
                "color": "#ffffff",
                "weight": 2.3,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["name"],
                aliases=["PROVINCE:"],
                sticky=False,
                style=(
                    "background-color: #18181b; color: #ffffff; "
                    "border: 1px solid #d4d4d8; font-family: 'Space Grotesk', sans-serif; "
                    "font-size: 11px; font-weight: 800; padding: 4px 8px;"
                ),
            ),
        ).add_to(sa_map)

    layers = {}
    counts = {key: 0 for key in CATEGORY_META}

    for key, meta in CATEGORY_META.items():
        fg = folium.FeatureGroup(name=meta["label"], show=True)
        fg.add_to(sa_map)
        layers[key] = fg

    for inc in incidents:
        cat = inc["category"]
        meta = CATEGORY_META[cat]
        counts[cat] += 1

        popup = folium.Popup(build_popup_html(inc), max_width=310)
        tooltip = f"[{meta['label']}] {inc['location_name']} ({inc['reported_at']})"

        folium.Marker(
            location=[inc["latitude"], inc["longitude"]],
            popup=popup,
            tooltip=tooltip,
            icon=build_custom_marker_icon(cat),
        ).add_to(layers[cat])

    folium.LayerControl(collapsed=False).add_to(sa_map)

    updated_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ui_html = f"""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@600;700;800&display=swap" rel="stylesheet">
    <style>
        .leaflet-tile-pane {{
            filter: grayscale(100%) brightness(1.08) contrast(1.12);
        }}
        .leaflet-container {{
            background: #27272a !important;
            font-family: 'Space Grotesk', system-ui, -apple-system, sans-serif;
            font-weight: 700;
        }}
        .leaflet-control-layers {{
            background: rgba(24, 24, 27, 0.96) !important;
            color: #ffffff !important;
            border: 1px solid #a1a1aa !important;
            border-radius: 8px !important;
            font-weight: 700 !important;
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.45) !important;
        }}
        .cr-hud {{
            position: fixed;
            top: 14px;
            left: 54px;
            z-index: 9999;
            background: rgba(24, 24, 27, 0.96);
            color: #ffffff;
            padding: 14px 18px;
            border-radius: 10px;
            border: 1px solid #a1a1aa;
            font-family: 'Space Grotesk', system-ui, -apple-system, sans-serif;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
            max-width: 380px;
        }}
        .cr-title {{
            font-size: 28px;
            font-weight: 800;
            letter-spacing: -0.02em;
            line-height: 1.02;
            color: #ef4444;
            text-transform: uppercase;
        }}
        .cr-subtitle {{
            font-size: 12px;
            color: #ffffff;
            font-weight: 700;
            margin-top: 6px;
            line-height: 1.3;
        }}
        .cr-stats {{
            display: flex;
            gap: 12px;
            margin-top: 10px;
            padding-top: 9px;
            border-top: 1px solid #71717a;
            font-size: 12px;
            font-weight: 700;
            color: #ffffff;
        }}
        .cr-bottom-bar {{
            position: fixed;
            bottom: 14px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 9999;
            display: inline-flex;
            align-items: center;
            gap: 16px;
            background: rgba(24, 24, 27, 0.96);
            color: #ffffff;
            padding: 8px 16px;
            border-radius: 999px;
            border: 1px solid #a1a1aa;
            font-family: 'Space Grotesk', system-ui, -apple-system, sans-serif;
            font-size: 12px;
            font-weight: 800;
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.45);
        }}
        .cr-link {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            color: #ffffff;
            font-weight: 800;
            text-decoration: none;
            transition: color 0.15s ease;
        }}
        .cr-link:hover {{
            color: #ef4444;
        }}
        .cr-divider {{
            color: #d4d4d8;
            font-weight: 800;
        }}
    </style>
    <div class="cr-hud">
        <div class="cr-title">CRIME RADR</div>
        <div class="cr-subtitle">
            South Africa &bull; Major Incidents Since 6 July 2025 (Madlanga Commission)
        </div>
        <div class="cr-stats">
            <span><strong style="color:#ef4444; font-weight:800;">{counts['drug_bust']}</strong> <span style="color:#ffffff;">Drug Busts</span></span>
            <span><strong style="color:#ef4444; font-weight:800;">{counts['hijacking']}</strong> <span style="color:#ffffff;">Hijackings</span></span>
            <span><strong style="color:#ef4444; font-weight:800;">{counts['cit_robbery']}</strong> <span style="color:#ffffff;">CIT Heists</span></span>
        </div>
        <div style="font-size: 10px; color: #e4e4e7; font-weight: 700; margin-top: 8px;">
            Auto-refreshed every 6h &bull; Last build: {updated_str}
        </div>
    </div>
    <div class="cr-bottom-bar">
        <a class="cr-link" href="https://x.com/PotwanaNeo" target="_blank" rel="noopener noreferrer" title="X / Twitter">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="#ef4444" aria-hidden="true">
                <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
            </svg>
            <span>@PotwanaNeo</span>
        </a>
        <span class="cr-divider">&bull;</span>
        <a class="cr-link" href="https://github.com/wanapo" target="_blank" rel="noopener noreferrer" title="GitHub">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="#ef4444" aria-hidden="true">
                <path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
            </svg>
            <span>@wanapo</span>
        </a>
    </div>
    """
    sa_map.get_root().html.add_child(folium.Element(ui_html))

    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    sa_map.save(str(OUTPUT_HTML))
    return OUTPUT_HTML


if __name__ == "__main__":
    out = generate_map()
    print(f"[OK] Static Crime Radr map generated at {out}")
