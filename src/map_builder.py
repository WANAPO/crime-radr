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

CATEGORY_META = {
    "drug_bust": {
        "label": "Major Drug Busts & Labs",
        "color": "purple",
        "badge_bg": "#dc2626",
        "icon": "exclamation-sign",
    },
    "hijacking": {
        "label": "Hijackings & Stolen Vehicles",
        "color": "orange",
        "badge_bg": "#b91c1c",
        "icon": "road",
    },
    "cit_robbery": {
        "label": "CIT Heists & Money Trucks",
        "color": "red",
        "badge_bg": "#991b1b",
        "icon": "fire",
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
        label = html.escape(k.replace("_", " ").title())
        val = html.escape(str(v))
        detail_rows += f"<div><strong style='color:#ef4444; font-weight:700;'>{label}:</strong> <span style='color:#ffffff; font-weight:600;'>{val}</span></div>"

    img_block = ""
    if gallery:
        img_tags = "".join(
            f'<img src="{html.escape(url)}" alt="Incident photo" '
            f'style="width:100%; max-height:150px; object-fit:cover; border-radius:4px; border:1px solid #52525b; margin-bottom:4px;">'
            for url in gallery[:3]
            if url
        )
        if img_tags:
            img_block = f'<div style="margin:8px 0;">{img_tags}</div>'

    return f"""
    <div style="font-family:'Space Grotesk',system-ui,-apple-system,sans-serif; width:275px; color:#ffffff; background:#18181b; border:1px solid #71717a; padding:11px; border-radius:8px;">
        <span style="display:inline-block; background:{meta['badge_bg']}; color:#ffffff; font-size:11px; font-weight:800; padding:2px 8px; border-radius:999px; text-transform:uppercase; letter-spacing:0.03em;">
            {html.escape(meta['label'])}
        </span>
        <h4 style="margin:8px 0 4px 0; font-size:14px; font-weight:800; color:#ffffff;">
            {html.escape(incident['title'])}
        </h4>
        <div style="font-size:11px; color:#d4d4d8; font-weight:600; margin-bottom:6px;">
            {html.escape(incident['reported_at'])} &bull; <span style="color:#ef4444; font-weight:700;">{html.escape(incident['location_name'])}</span> ({html.escape(incident.get('province', ''))})
        </div>
        {img_block}
        <p style="font-size:12px; line-height:1.4; color:#f4f4f5; font-weight:500; margin:6px 0;">
            {html.escape(incident['summary'])}
        </p>
        <div style="font-size:12px; background:#27272a; border:1px solid #52525b; padding:7px 9px; border-radius:5px; margin:6px 0; color:#ffffff;">
            {detail_rows}
        </div>
        <a href="{html.escape(incident['source_url'])}" target="_blank" rel="noopener noreferrer"
           style="display:inline-block; margin-top:4px; font-size:12px; color:#ef4444; text-decoration:none; font-weight:800;">
            VIEW SOURCE POST &rarr;
        </a>
    </div>
    """


def generate_map() -> Path:
    init_db()
    incidents = fetch_all_incidents()

    sa_map = folium.Map(
        location=[-28.8, 24.8],
        zoom_start=6,
        tiles=None,
        control_scale=True,
    )

    # Grey & light-grey tactical line basemap (zero API keys, works over file:// and http://)
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

    # Light-grey lines for national & provincial boundaries over grey landmass
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
            icon=folium.Icon(color=meta["color"], icon=meta["icon"], prefix="glyphicon"),
        ).add_to(layers[cat])

    folium.LayerControl(collapsed=False).add_to(sa_map)

    updated_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ui_html = f"""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@600;700;800&display=swap" rel="stylesheet">
    <style>
        /* Grey & light-grey line map tuning */
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
