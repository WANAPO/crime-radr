from datetime import datetime, timezone
import html
from pathlib import Path
import folium
from src.db import fetch_all_incidents, init_db

OUTPUT_HTML = Path("output/index.html")

CATEGORY_META = {
    "drug_bust": {
        "label": "Major Drug Busts & Labs",
        "color": "purple",
        "badge_bg": "#7e22ce",
        "icon": "exclamation-sign",
    },
    "hijacking": {
        "label": "Hijackings & Stolen Vehicles",
        "color": "orange",
        "badge_bg": "#d97706",
        "icon": "road",
    },
    "cit_robbery": {
        "label": "CIT Heists & Money Trucks",
        "color": "red",
        "badge_bg": "#dc2626",
        "icon": "fire",
    },
}


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
        detail_rows += f"<div><strong>{label}:</strong> {val}</div>"

    img_block = ""
    if gallery:
        img_tags = "".join(
            f'<img src="{html.escape(url)}" alt="Incident photo" '
            f'style="width:100%; max-height:150px; object-fit:cover; border-radius:4px; border:1px solid #333; margin-bottom:4px;">'
            for url in gallery[:3]
            if url
        )
        if img_tags:
            img_block = f'<div style="margin:8px 0;">{img_tags}</div>'

    return f"""
    <div style="font-family:'Space Grotesk',system-ui,-apple-system,sans-serif; width:275px; color:#f3f4f6; background:#111827; padding:10px; border-radius:6px;">
        <span style="display:inline-block; background:{meta['badge_bg']}; color:#fff; font-size:11px; font-weight:700; padding:2px 8px; border-radius:999px; text-transform:uppercase;">
            {html.escape(meta['label'])}
        </span>
        <h4 style="margin:8px 0 4px 0; font-size:14px; color:#ffffff;">
            {html.escape(incident['title'])}
        </h4>
        <div style="font-size:11px; color:#9ca3af; margin-bottom:6px;">
            {html.escape(incident['reported_at'])} &bull; {html.escape(incident['location_name'])} ({html.escape(incident.get('province', ''))})
        </div>
        {img_block}
        <p style="font-size:12px; line-height:1.4; color:#d1d5db; margin:6px 0;">
            {html.escape(incident['summary'])}
        </p>
        <div style="font-size:12px; background:#1f2937; padding:6px 8px; border-radius:4px; margin:6px 0; color:#e5e7eb;">
            {detail_rows}
        </div>
        <a href="{html.escape(incident['source_url'])}" target="_blank" rel="noopener noreferrer"
           style="display:inline-block; margin-top:4px; font-size:12px; color:#60a5fa; text-decoration:none; font-weight:600;">
            View Source Post &rarr;
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

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ",
        name="Dark Gray Canvas",
        control=False,
    ).add_to(sa_map)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
        attr="Labels &copy; Esri",
        name="City & Highway Labels",
        overlay=True,
        control=False,
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
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700;800&display=swap" rel="stylesheet">
    <style>
        .leaflet-tile-pane {{
            filter: invert(100%) hue-rotate(180deg) brightness(92%) contrast(92%);
        }}
        .leaflet-container {{
            background: #0b0f19 !important;
            font-family: 'Space Grotesk', system-ui, -apple-system, sans-serif;
        }}
        .cr-hud {{
            position: fixed;
            top: 14px;
            left: 54px;
            z-index: 9999;
            background: rgba(15, 23, 42, 0.94);
            color: #f9fafb;
            padding: 14px 18px;
            border-radius: 10px;
            border: 1px solid #334155;
            font-family: 'Space Grotesk', system-ui, -apple-system, sans-serif;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.55);
            max-width: 370px;
        }}
        .cr-title {{
            font-size: 26px;
            font-weight: 800;
            letter-spacing: -0.02em;
            line-height: 1.05;
            color: #f87171;
            text-transform: uppercase;
        }}
        .cr-subtitle {{
            font-size: 12px;
            color: #cbd5e1;
            margin-top: 5px;
            line-height: 1.3;
        }}
        .cr-stats {{
            display: flex;
            gap: 12px;
            margin-top: 10px;
            padding-top: 9px;
            border-top: 1px solid rgba(148, 163, 184, 0.18);
            font-size: 12px;
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
            background: rgba(15, 23, 42, 0.94);
            color: #e2e8f0;
            padding: 8px 16px;
            border-radius: 999px;
            border: 1px solid #334155;
            font-family: 'Space Grotesk', system-ui, -apple-system, sans-serif;
            font-size: 12px;
            font-weight: 600;
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.55);
        }}
        .cr-link {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            color: #f8fafc;
            text-decoration: none;
            transition: color 0.15s ease;
        }}
        .cr-link:hover {{
            color: #38bdf8;
        }}
        .cr-divider {{
            color: #475569;
        }}
    </style>
    <div class="cr-hud">
        <div class="cr-title">CRIME RADR</div>
        <div class="cr-subtitle">
            South Africa &bull; Major Incidents Since 6 July 2025 (Madlanga Commission)
        </div>
        <div class="cr-stats">
            <span><strong style="color:#c084fc;">{counts['drug_bust']}</strong> Drug Busts</span>
            <span><strong style="color:#fbbf24;">{counts['hijacking']}</strong> Hijackings</span>
            <span><strong style="color:#f87171;">{counts['cit_robbery']}</strong> CIT Heists</span>
        </div>
        <div style="font-size: 10px; color: #64748b; margin-top: 8px;">
            Auto-refreshed every 6h &bull; Last build: {updated_str}
        </div>
    </div>
    <div class="cr-bottom-bar">
        <a class="cr-link" href="https://x.com/PotwanaNeo" target="_blank" rel="noopener noreferrer" title="X / Twitter">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
            </svg>
            <span>@PotwanaNeo</span>
        </a>
        <span class="cr-divider">&bull;</span>
        <a class="cr-link" href="https://github.com/wanapo" target="_blank" rel="noopener noreferrer" title="GitHub">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
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
