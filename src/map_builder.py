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

    video_url = details.pop("video_url", None)

    detail_rows = ""
    for k, v in details.items():
        label = html.escape(k.replace("_", " ").title())
        val = html.escape(str(v))
        detail_rows += f"<div><strong>{label}:</strong> {val}</div>"

    gallery_block = ""
    if gallery:
        thumbs = ""
        for idx, img_src in enumerate(gallery):
            safe_img = html.escape(img_src)
            width_style = "100%" if len(gallery) == 1 else "125px"
            height_style = "155px" if len(gallery) == 1 else "95px"
            thumbs += (
                f'<a href="{safe_img}" target="_blank" rel="noopener noreferrer">'
                f'<img src="{safe_img}" alt="Incident photo {idx + 1}" '
                f'style="width:{width_style}; height:{height_style}; object-fit:cover; '
                f'border-radius:4px; border:1px solid #374151; flex-shrink:0;">'
                f"</a>"
            )
        gallery_block = f"""
        <div style="margin:8px 0;">
            <div style="display:flex; gap:6px; overflow-x:auto; padding-bottom:4px;">
                {thumbs}
            </div>
            {f'<div style="font-size:10px; color:#9ca3af;">Gallery ({len(gallery)} photos) &bull; Click image to enlarge</div>' if len(gallery) > 1 else ''}
        </div>
        """

    video_btn = ""
    if video_url:
        safe_vid = html.escape(video_url)
        video_btn = f"""
        <a href="{safe_vid}" target="_blank" rel="noopener noreferrer"
           style="display:inline-block; margin-top:6px; margin-right:8px; padding:4px 8px;
                  background:#dc2626; color:#ffffff; font-size:11px; border-radius:4px;
                  text-decoration:none; font-weight:700;">
            &#9654; Watch Footage
        </a>
        """

    return f"""
    <div style="font-family:system-ui,-apple-system,sans-serif; width:285px; color:#f3f4f6; background:#111827; padding:10px; border-radius:6px;">
        <span style="display:inline-block; background:{meta['badge_bg']}; color:#fff; font-size:11px; font-weight:700; padding:2px 8px; border-radius:999px; text-transform:uppercase;">
            {html.escape(meta['label'])}
        </span>
        <h4 style="margin:8px 0 4px 0; font-size:14px; color:#ffffff;">
            {html.escape(incident['title'])}
        </h4>
        <div style="font-size:11px; color:#9ca3af; margin-bottom:6px;">
            {html.escape(incident['reported_at'])} &bull; {html.escape(incident['location_name'])} ({html.escape(incident.get('province', ''))})
        </div>
        {gallery_block}
        <p style="font-size:12px; line-height:1.4; color:#d1d5db; margin:6px 0;">
            {html.escape(incident['summary'])}
        </p>
        <div style="font-size:12px; background:#1f2937; padding:6px 8px; border-radius:4px; margin:6px 0; color:#e5e7eb;">
            {detail_rows}
        </div>
        <div>
            {video_btn}
            <a href="{html.escape(incident['source_url'])}" target="_blank" rel="noopener noreferrer"
               style="display:inline-block; margin-top:6px; font-size:12px; color:#60a5fa; text-decoration:none; font-weight:600;">
                View Source &rarr;
            </a>
        </div>
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

        popup = folium.Popup(build_popup_html(inc), max_width=315)
        tooltip = f"[{meta['label']}] {inc['location_name']} ({inc['reported_at']})"

        folium.Marker(
            location=[inc["latitude"], inc["longitude"]],
            popup=popup,
            tooltip=tooltip,
            icon=folium.Icon(color=meta["color"], icon=meta["icon"], prefix="glyphicon"),
        ).add_to(layers[cat])

    folium.LayerControl(collapsed=False).add_to(sa_map)

    updated_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    hud_html = f"""
    <div style="
        position: fixed;
        top: 14px;
        left: 54px;
        z-index: 9999;
        background: rgba(17, 24, 39, 0.92);
        color: #f9fafb;
        padding: 12px 16px;
        border-radius: 8px;
        border: 1px solid #374151;
        font-family: system-ui, -apple-system, sans-serif;
        box-shadow: 0 4px 14px rgba(0,0,0,0.5);
        max-width: 360px;
    ">
        <div style="font-size: 16px; font-weight: 800; letter-spacing: 0.5px; color: #f87171;">
            CRIME RADR &bull; SOUTH AFRICA
        </div>
        <div style="font-size: 11px; color: #9ca3af; margin-top: 2px;">
            Tracking Major Incidents Since 6 July 2025 (Madlanga Commission)
        </div>
        <div style="display:flex; gap:10px; margin-top:8px; font-size:12px;">
            <span><strong style="color:#c084fc;">{counts['drug_bust']}</strong> Drug Busts</span>
            <span><strong style="color:#fbbf24;">{counts['hijacking']}</strong> Stolen/Hijacked</span>
            <span><strong style="color:#f87171;">{counts['cit_robbery']}</strong> CIT Heists</span>
        </div>
        <div style="font-size: 10px; color: #6b7280; margin-top: 6px;">
            Auto-refreshed every 6h &bull; Last build: {updated_str}
        </div>
    </div>
    """
    sa_map.get_root().html.add_child(folium.Element(hud_html))

    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    sa_map.save(str(OUTPUT_HTML))
    return OUTPUT_HTML


if __name__ == "__main__":
    out = generate_map()
    print(f"[OK] Static Crime Radr map generated at {out}")
