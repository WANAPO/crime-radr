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
  <path d="M5 17L8 10.5C8.5 9.5 9.5 9 10.6 9H18.4C19.5 9 20.5 9.5 21 10.5L24 17H26.5C27.9 17 29 18.1 29 19.5V22H26.8C26.4 20.3 24.9 19 23.1 19C21.3 19 19.8 20.3 19.4 22H12.6C12.2 20.3 10.7 19 8.9 19C7.1 19 5.6 20.3 5.2 22H3V19.5C3 18.1 3.9 17 5 17Z" fill="#ffffff" stroke="#111827" stroke-width="1.3"/>
  <circle cx="8.9" cy="22" r="2.2" fill="#dc2626" stroke="#111827" stroke-width="1.2"/>
  <circle cx="23.1" cy="22" r="2.2" fill="#dc2626" stroke="#111827" stroke-width="1.2"/>
  <g transform="translate(19, 1) rotate(28)">
    <rect x="0" y="0" width="14" height="7.5" rx="3.75" fill="#ffffff" stroke="#111827" stroke-width="1.2"/>
    <path d="M7 0.6H10.25C12.1 0.6 13.4 2 13.4 3.75C13.4 5.5 12.1 6.9 10.25 6.9H7V0.6Z" fill="#a855f7"/>
  </g>
</svg>
"""

TINY_UBERCARD_SVG = """
<svg width="24" height="22" viewBox="0 0 32 26" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M7.5 16.5L10.2 8.5C10.6 7.4 11.6 6.8 12.8 6.8H19.2C20.4 6.8 21.4 7.4 21.8 8.5L24.5 16.5H26.2C27.5 16.5 28.5 17.5 28.5 18.8V20.5H26.4C26 18.8 24.5 17.6 22.8 17.6C21.1 17.6 19.6 18.8 19.2 20.5H12.8C12.4 18.8 10.9 17.6 9.2 17.6C7.5 17.6 6 18.8 5.6 20.5H3.5V18.8C3.5 17.5 4.5 16.5 5.8 16.5H7.5Z" fill="#ffffff" stroke="#111827" stroke-width="1.3"/>
  <path d="M11.2 15.5L12.8 9.2H19.2L20.8 15.5H11.2Z" fill="#3f3f46"/>
  <circle cx="9.2" cy="20.5" r="2.2" fill="#f59e0b" stroke="#111827" stroke-width="1.2"/>
  <circle cx="22.8" cy="20.5" r="2.2" fill="#f59e0b" stroke="#111827" stroke-width="1.2"/>
</svg>
"""

CIT_CASH_TRUCK_SVG = """
<svg width="30" height="24" viewBox="0 0 40 28" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="11" y="7" width="16" height="13" rx="1.8" fill="#ffffff" stroke="#111827" stroke-width="1.3"/>
  <path d="M27 11H32.5L35.5 15V20H27V11Z" fill="#e4e4e7" stroke="#111827" stroke-width="1.3"/>
  <rect x="28.8" y="12.5" width="4.2" height="3.2" rx="0.6" fill="#3f3f46"/>
  <rect x="2" y="8" width="6.5" height="3.6" rx="0.7" transform="rotate(-18 2 8)" fill="#22c55e" stroke="#111827" stroke-width="1"/>
  <rect x="1" y="13.2" width="6.5" height="3.6" rx="0.7" transform="rotate(14 1 13.2)" fill="#4ade80" stroke="#111827" stroke-width="1"/>
  <rect x="4.5" y="17.5" width="6" height="3.4" rx="0.7" transform="rotate(-10 4.5 17.5)" fill="#16a34a" stroke="#111827" stroke-width="1"/>
  <circle cx="15.5" cy="21" r="2.5" fill="#ef4444" stroke="#111827" stroke-width="1.2"/>
  <circle cx="31.5" cy="21" r="2.5" fill="#ef4444" stroke="#111827" stroke-width="1.2"/>
</svg>
"""

CATEGORY_META = {
    "drug_bust": {
        "label": "Major Drug Busts & Labs",
        "short": "Drug Busts",
        "color": "#a855f7",
        "badge_bg": "#dc2626",
        "svg": DRUG_CAR_SVG,
    },
    "hijacking": {
        "label": "Hijackings & Stolen Vehicles",
        "short": "Hijackings",
        "color": "#f59e0b",
        "badge_bg": "#b91c1c",
        "svg": TINY_UBERCARD_SVG,
    },
    "cit_robbery": {
        "label": "CIT Heists & Money Trucks",
        "short": "CIT Heists",
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


def _clean_display_summary(title: str, summary: str) -> str:
    if not summary:
        return ""
    t_norm = "".join(ch.lower() for ch in title if ch.isalnum())
    s_norm = "".join(ch.lower() for ch in summary if ch.isalnum())
    if not s_norm or t_norm == s_norm or t_norm in s_norm or s_norm in t_norm:
        return ""
    return summary.strip()


def build_popup_html(incident: dict) -> str:
    meta = CATEGORY_META[incident["category"]]
    details = dict(incident.get("details", {}))

    gallery = details.pop("gallery", [])
    if not gallery and incident.get("image_url"):
        gallery = [incident["image_url"]]

    source_label = html.escape(str(details.pop("source", "SA Press") or "SA Press"))
    precision_label = html.escape(str(details.pop("precision", "Town / Suburb") or "Town / Suburb"))

    detail_rows = ""
    for k, v in details.items():
        label = html.escape(k.replace("_", " ").upper())
        val_str = str(v).strip() or "N/A"
        val = html.escape(val_str)
        detail_rows += (
            f"<div style='margin:2px 0;'>"
            f"<strong style='color:#ef4444; font-weight:700;'>{label}:</strong> "
            f"<span style='color:#ffffff; font-weight:600;'>{val}</span>"
            f"</div>"
        )

    img_block = ""
    if gallery:
        img_tags = "".join(
            f'<img src="{html.escape(url)}" alt="Incident photo" '
            f'style="width:100%; max-height:130px; object-fit:cover; border-radius:2px; border:1px solid #3f3f46; margin-bottom:4px;" '
            f'onerror="this.style.display=\'none\';">'
            for url in gallery[:2]
            if url
        )
        if img_tags:
            img_block = f'<div style="margin:6px 0;">{img_tags}</div>'

    clean_sum = _clean_display_summary(incident.get("title", ""), incident.get("summary", ""))
    summary_html = (
        f"<p style='font-size:12px; line-height:1.3; color:#f4f4f5; margin:5px 0;'>{html.escape(clean_sum)}</p>"
        if clean_sum
        else ""
    )

    return f"""
    <div style="font-family:'Times New Roman',Times,Georgia,serif; width:265px; color:#ffffff; background:#141416; padding:6px;">
        <div style="display:flex; justify-content:space-between; align-items:center; gap:4px;">
            <span style="display:inline-block; background:{meta['badge_bg']}; color:#ffffff; font-size:10px; font-weight:700; padding:2px 7px; border-radius:2px; text-transform:uppercase; letter-spacing:0.04em;">
                {html.escape(meta['label'])}
            </span>
            <span style="font-size:10px; color:#d4d4d8; border:1px solid #52525b; padding:1px 5px; border-radius:2px;">
                {source_label}
            </span>
        </div>
        <h4 style="margin:6px 0 3px 0; font-size:14px; font-weight:700; color:#ffffff; line-height:1.2;">
            {html.escape(incident['title'])}
        </h4>
        <div style="font-size:11px; color:#d4d4d8; margin-bottom:5px;">
            {html.escape(incident['reported_at'])} &bull; {html.escape(incident.get('province', 'N/A'))} &bull; <span style="color:#fca5a5;">{precision_label}</span>
        </div>
        {img_block}
        <div style="font-size:12px; background:#1f1f23; border:1px solid #3f3f46; padding:5px 7px; border-radius:2px; margin:5px 0; color:#ffffff;">
            {detail_rows}
        </div>
        {summary_html}
        <a href="{html.escape(incident['source_url'])}" target="_blank" rel="noopener noreferrer"
           style="display:inline-block; margin-top:4px; font-size:11px; color:#ef4444; text-decoration:none; font-weight:700; letter-spacing:0.03em;">
            VERIFY SOURCE STATEMENT &rarr;
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
            background: rgba(20, 20, 22, 0.95);
            border: 1.5px solid {border_col};
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.65);
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

    # Include Leaflet.markercluster CSS & JS for dense hub grouping (Gauteng & KZN)
    cluster_assets = folium.Element("""
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/MarkerCluster.css" />
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/MarkerCluster.Default.css" />
    <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/leaflet.markercluster.js"></script>
    """)
    sa_map.get_root().header.add_child(cluster_assets)

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
                    "background-color: #141416; color: #ffffff; "
                    "border: 1px solid #52525b; font-family: 'Times New Roman', Times, Georgia, serif; "
                    "font-size: 12px; font-weight: 700; padding: 3px 7px;"
                ),
            ),
        ).add_to(sa_map)

    counts = {key: 0 for key in CATEGORY_META}
    records_for_js: list[dict] = []

    for inc in incidents:
        cat = inc["category"]
        if cat not in CATEGORY_META:
            continue
        counts[cat] += 1
        details_copy = dict(inc.get("details", {}))
        source_outlet = details_copy.get("source", "SA Press")
        precision = details_copy.get("precision", "Town / Suburb")
        records_for_js.append(
            {
                "category": cat,
                "title": inc.get("title", ""),
                "summary": _clean_display_summary(inc.get("title", ""), inc.get("summary", "")),
                "location_name": inc.get("location_name", ""),
                "province": inc.get("province", "South Africa"),
                "latitude": inc["latitude"],
                "longitude": inc["longitude"],
                "reported_at": inc.get("reported_at", ""),
                "source_url": inc.get("source_url", ""),
                "source": source_outlet,
                "precision": precision,
                "popup_html": build_popup_html(inc),
                "tooltip": f"[{CATEGORY_META[cat]['label']}] {inc.get('location_name', '')} ({inc.get('reported_at', '')})",
            }
        )

    map_var = sa_map.get_name()
    updated_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    records_json = json.dumps(records_for_js, ensure_ascii=False)
    meta_json = json.dumps(
        {
            k: {
                "label": v["label"],
                "short": v["short"],
                "color": v["color"],
                "svg": v["svg"].strip(),
            }
            for k, v in CATEGORY_META.items()
        },
        ensure_ascii=False,
    )

    ui_html = f"""
    <style>
        .leaflet-tile-pane {{
            filter: grayscale(100%) brightness(1.08) contrast(1.12);
        }}
        .leaflet-container {{
            background: #27272a !important;
            font-family: 'Times New Roman', Times, Georgia, serif;
        }}
        .leaflet-popup-content-wrapper,
        .leaflet-popup-tip {{
            background: #141416 !important;
            color: #ffffff !important;
            border: 1px solid #3f3f46 !important;
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.75) !important;
            border-radius: 3px !important;
        }}
        .leaflet-popup-content {{
            margin: 4px 6px !important;
        }}
        .leaflet-popup-close-button {{
            color: #ffffff !important;
            font-size: 16px !important;
        }}
        .leaflet-control-layers {{
            display: none !important;
        }}
        .cr-cluster-badge {{
            background: rgba(20, 20, 22, 0.96);
            border: 2px solid #ef4444;
            color: #ffffff;
            font-family: 'Times New Roman', Times, Georgia, serif;
            font-weight: 700;
            font-size: 12px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 3px 10px rgba(0, 0, 0, 0.75);
        }}
        .cr-hud {{
            position: fixed;
            top: 12px;
            left: 54px;
            z-index: 9999;
            background: rgba(20, 20, 22, 0.96);
            color: #ffffff;
            padding: 11px 15px;
            border-radius: 3px;
            border: 1px solid #52525b;
            font-family: 'Times New Roman', Times, Georgia, serif;
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.55);
            max-width: 390px;
        }}
        .cr-title {{
            font-size: 28px;
            font-weight: 700;
            letter-spacing: 0.02em;
            line-height: 1.0;
            color: #ef4444;
            text-transform: uppercase;
        }}
        .cr-subtitle {{
            font-size: 12px;
            color: #ffffff;
            font-weight: 700;
            margin-top: 4px;
            line-height: 1.25;
        }}
        .cr-stats {{
            display: flex;
            gap: 12px;
            margin-top: 8px;
            padding-top: 7px;
            border-top: 1px solid #52525b;
            font-size: 12px;
            font-weight: 700;
            color: #ffffff;
        }}
        .cr-filters {{
            position: fixed;
            top: 12px;
            right: 14px;
            z-index: 9999;
            width: 265px;
            background: rgba(20, 20, 22, 0.96);
            color: #ffffff;
            padding: 10px 12px;
            border-radius: 3px;
            border: 1px solid #52525b;
            font-family: 'Times New Roman', Times, Georgia, serif;
            font-size: 12px;
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.55);
        }}
        .cr-filter-row {{
            margin-top: 6px;
        }}
        .cr-filter-row label {{
            display: block;
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: #d4d4d8;
            font-weight: 700;
            margin-bottom: 2px;
        }}
        .cr-input, .cr-select {{
            width: 100%;
            box-sizing: border-box;
            background: #1f1f23;
            color: #ffffff;
            border: 1px solid #52525b;
            border-radius: 2px;
            padding: 4px 6px;
            font-family: 'Times New Roman', Times, Georgia, serif;
            font-size: 12px;
        }}
        .cr-cat-checks {{
            display: flex;
            flex-direction: column;
            gap: 4px;
            margin-top: 6px;
            padding-top: 6px;
            border-top: 1px solid #3f3f46;
        }}
        .cr-cat-checks label {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            font-weight: 700;
            color: #ffffff;
            cursor: pointer;
        }}
        .cr-drawer {{
            position: fixed;
            bottom: 52px;
            left: 14px;
            z-index: 9999;
            width: 280px;
            background: rgba(20, 20, 22, 0.96);
            color: #ffffff;
            border-radius: 3px;
            border: 1px solid #52525b;
            font-family: 'Times New Roman', Times, Georgia, serif;
            font-size: 12px;
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.55);
        }}
        .cr-drawer-head {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 7px 10px;
            cursor: pointer;
            font-weight: 700;
            background: #1f1f23;
            border-bottom: 1px solid #3f3f46;
        }}
        .cr-drawer-body {{
            padding: 8px 10px;
            max-height: 175px;
            overflow-y: auto;
        }}
        .cr-prov-row {{
            display: flex;
            justify-content: space-between;
            padding: 2px 0;
            border-bottom: 1px dotted #3f3f46;
        }}
        .cr-btn-reset {{
            margin-top: 7px;
            width: 100%;
            background: #b91c1c;
            color: #ffffff;
            border: 1px solid #ef4444;
            border-radius: 2px;
            padding: 4px 8px;
            font-family: 'Times New Roman', Times, Georgia, serif;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            cursor: pointer;
        }}
        .cr-bottom-bar {{
            position: fixed;
            bottom: 12px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 9999;
            display: inline-flex;
            align-items: center;
            gap: 14px;
            background: rgba(20, 20, 22, 0.96);
            color: #ffffff;
            padding: 6px 14px;
            border-radius: 3px;
            border: 1px solid #52525b;
            font-family: 'Times New Roman', Times, Georgia, serif;
            font-size: 13px;
            font-weight: 700;
            box-shadow: 0 6px 16px rgba(0, 0, 0, 0.55);
        }}
        .cr-link {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            color: #ffffff;
            font-weight: 700;
            text-decoration: none;
        }}
        .cr-link:hover {{
            color: #ef4444;
        }}
        .cr-divider {{
            color: #a1a1aa;
            font-weight: 700;
        }}
    </style>

    <div class="cr-hud">
        <div class="cr-title">CRIME RADR</div>
        <div class="cr-subtitle">
            South Africa &bull; Major Incidents Since 6 July 2025 (Madlanga Commission)
        </div>
        <div class="cr-stats" id="cr-hud-counts">
            <span><strong style="color:#ef4444;">{counts['drug_bust']}</strong> Drug Busts</span>
            <span><strong style="color:#ef4444;">{counts['hijacking']}</strong> Hijackings</span>
            <span><strong style="color:#ef4444;">{counts['cit_robbery']}</strong> CIT Heists</span>
        </div>
        <div style="font-size: 11px; color: #d4d4d8; margin-top: 6px;">
            Auto-refreshed every 6h &bull; Last build: {updated_str}
        </div>
    </div>

    <div class="cr-filters">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <strong style="color:#ef4444; text-transform:uppercase; letter-spacing:0.04em;">Researcher Filters</strong>
            <span id="cr-visible-badge" style="color:#d4d4d8; font-size:11px;">{len(records_for_js)} shown</span>
        </div>
        <div class="cr-filter-row">
            <label for="cr-search">Keyword / Location / Source</label>
            <input id="cr-search" class="cr-input" type="text" placeholder="e.g. Margate, N3, cocaine, SAPS..." />
        </div>
        <div class="cr-filter-row">
            <label for="cr-province">Province</label>
            <select id="cr-province" class="cr-select">
                <option value="ALL">All Provinces</option>
                <option value="KwaZulu-Natal">KwaZulu-Natal</option>
                <option value="Gauteng">Gauteng</option>
                <option value="Western Cape">Western Cape</option>
                <option value="Eastern Cape">Eastern Cape</option>
                <option value="Free State">Free State</option>
                <option value="Limpopo">Limpopo</option>
                <option value="Mpumalanga">Mpumalanga</option>
                <option value="North West">North West</option>
                <option value="Northern Cape">Northern Cape</option>
            </select>
        </div>
        <div class="cr-filter-row">
            <label for="cr-window">Time Window</label>
            <select id="cr-window" class="cr-select">
                <option value="ALL">Since 6 July 2025 (All)</option>
                <option value="7">Last 7 Days</option>
                <option value="30">Last 30 Days</option>
            </select>
        </div>
        <div class="cr-cat-checks">
            <label><input type="checkbox" class="cr-cat-cb" value="drug_bust" checked /> Major Drug Busts &amp; Labs</label>
            <label><input type="checkbox" class="cr-cat-cb" value="hijacking" checked /> Hijackings &amp; Stolen Vehicles</label>
            <label><input type="checkbox" class="cr-cat-cb" value="cit_robbery" checked /> CIT Heists &amp; Money Trucks</label>
        </div>
        <button id="cr-reset-btn" class="cr-btn-reset" type="button">Reset Filters</button>
    </div>

    <div class="cr-drawer">
        <div class="cr-drawer-head" id="cr-drawer-toggle">
            <span>Provincial &amp; Trend Summary</span>
            <span id="cr-drawer-arrow">&#9660;</span>
        </div>
        <div class="cr-drawer-body" id="cr-drawer-body"></div>
    </div>

    <div class="cr-bottom-bar">
        <a class="cr-link" href="https://x.com/PotwanaNeo" target="_blank" rel="noopener noreferrer" title="X / Twitter">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="#ef4444" aria-hidden="true">
                <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
            </svg>
            <span>@PotwanaNeo</span>
        </a>
        <span class="cr-divider">&bull;</span>
        <a class="cr-link" href="https://github.com/wanapo" target="_blank" rel="noopener noreferrer" title="GitHub">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="#ef4444" aria-hidden="true">
                <path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
            </svg>
            <span>@wanapo</span>
        </a>
    </div>

    <script>
    (function() {{
        const INCIDENTS = {records_json};
        const META = {meta_json};
        const mapObj = {map_var};

        const clusterGroup = L.markerClusterGroup({{
            maxClusterRadius: 42,
            spiderfyOnMaxZoom: true,
            showCoverageOnHover: false,
            iconCreateFunction: function(cluster) {{
                const count = cluster.getChildCount();
                const size = count >= 25 ? 40 : count >= 10 ? 35 : 30;
                return L.divIcon({{
                    html: '<div class="cr-cluster-badge" style="width:' + size + 'px;height:' + size + 'px;">' + count + '</div>',
                    className: '',
                    iconSize: [size, size],
                    iconAnchor: [size / 2, size / 2]
                }});
            }}
        }});
        mapObj.addLayer(clusterGroup);

        function makeIcon(cat) {{
            const m = META[cat] || META.cit_robbery;
            return L.divIcon({{
                html: '<div style="width:34px;height:30px;margin-left:-17px;margin-top:-15px;background:rgba(20,20,22,0.95);border:1.5px solid ' + m.color + ';border-radius:4px;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 6px rgba(0,0,0,0.65);">' + m.svg + '</div>',
                className: '',
                iconSize: [34, 30],
                iconAnchor: [17, 15]
            }});
        }}

        function withinWindow(dateStr, days) {{
            if (days === "ALL" || !dateStr) return true;
            const parsed = Date.parse(dateStr + "T00:00:00Z");
            if (Number.isNaN(parsed)) return true;
            const cutoff = Date.now() - (parseInt(days, 10) * 86400000);
            return parsed >= cutoff;
        }}

        function renderFiltered() {{
            const q = (document.getElementById("cr-search").value || "").trim().toLowerCase();
            const prov = document.getElementById("cr-province").value;
            const win = document.getElementById("cr-window").value;
            const activeCats = new Set(
                Array.from(document.querySelectorAll(".cr-cat-cb:checked")).map(cb => cb.value)
            );

            const filtered = INCIDENTS.filter(item => {{
                if (!activeCats.has(item.category)) return false;
                if (prov !== "ALL" && item.province !== prov) return false;
                if (!withinWindow(item.reported_at, win)) return false;
                if (q) {{
                    const hay = [item.title, item.summary, item.location_name, item.province, item.source, item.reported_at]
                        .join(" ").toLowerCase();
                    if (!hay.includes(q)) return false;
                }}
                return true;
            }});

            clusterGroup.clearLayers();
            const newMarkers = [];
            const catCounts = {{ drug_bust: 0, hijacking: 0, cit_robbery: 0 }};
            const provCounts = {{}};
            let recent7d = 0;

            filtered.forEach(item => {{
                if (typeof item.latitude !== "number" || typeof item.longitude !== "number") return;
                catCounts[item.category] = (catCounts[item.category] || 0) + 1;
                provCounts[item.province] = (provCounts[item.province] || 0) + 1;
                if (withinWindow(item.reported_at, "7")) recent7d += 1;

                const marker = L.marker([item.latitude, item.longitude], {{ icon: makeIcon(item.category) }});
                marker.bindPopup(item.popup_html, {{ maxWidth: 290 }});
                marker.bindTooltip(item.tooltip);
                newMarkers.push(marker);
            }});

            clusterGroup.addLayers(newMarkers);

            document.getElementById("cr-hud-counts").innerHTML =
                '<span><strong style="color:#ef4444;">' + catCounts.drug_bust + '</strong> Drug Busts</span>' +
                '<span><strong style="color:#ef4444;">' + catCounts.hijacking + '</strong> Hijackings</span>' +
                '<span><strong style="color:#ef4444;">' + catCounts.cit_robbery + '</strong> CIT Heists</span>';

            document.getElementById("cr-visible-badge").textContent = filtered.length + " shown";

            const sortedProvs = Object.entries(provCounts).sort((a, b) => b[1] - a[1]);
            const provHtml = sortedProvs.length
                ? sortedProvs.map(([p, c]) => '<div class="cr-prov-row"><span>' + p + '</span><strong>' + c + '</strong></div>').join("")
                : '<div style="color:#a1a1aa;">No matching incidents</div>';

            document.getElementById("cr-drawer-body").innerHTML =
                '<div style="margin-bottom:6px; color:#fca5a5; font-weight:700;">Last 7 Days in View: ' + recent7d + '</div>' +
                provHtml;
        }}

        document.getElementById("cr-search").addEventListener("input", renderFiltered);
        document.getElementById("cr-province").addEventListener("change", renderFiltered);
        document.getElementById("cr-window").addEventListener("change", renderFiltered);
        document.querySelectorAll(".cr-cat-cb").forEach(cb => cb.addEventListener("change", renderFiltered));

        document.getElementById("cr-reset-btn").addEventListener("click", function() {{
            document.getElementById("cr-search").value = "";
            document.getElementById("cr-province").value = "ALL";
            document.getElementById("cr-window").value = "ALL";
            document.querySelectorAll(".cr-cat-cb").forEach(cb => {{ cb.checked = true; }});
            renderFiltered();
        }});

        document.getElementById("cr-drawer-toggle").addEventListener("click", function() {{
            const body = document.getElementById("cr-drawer-body");
            const arrow = document.getElementById("cr-drawer-arrow");
            const hidden = body.style.display === "none";
            body.style.display = hidden ? "block" : "none";
            arrow.innerHTML = hidden ? "&#9660;" : "&#9650;";
        }});

        renderFiltered();
    }})();
    </script>
    """
    sa_map.get_root().html.add_child(folium.Element(ui_html))

    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    sa_map.save(str(OUTPUT_HTML))
    return OUTPUT_HTML


if __name__ == "__main__":
    out = generate_map()
    print(f"[OK] Static Crime Radr map generated at {out}")
