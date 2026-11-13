"""Vocabulary of the shipping data: vessel types, port metrics, cargo and event types.

Shared by the monitor metrics and the app; the values are PortWatch column names.
"""

# Vessel-count columns of PortWatch and the names used in the app.
VESSEL_TYPES = {
    "total": "n_total",
    "container": "n_container",
    "tanker": "n_tanker",
    "dry_bulk": "n_dry_bulk",
    "general_cargo": "n_general_cargo",
    "roro": "n_roro",
}

# Port metrics of PortWatch: calls (vessels per day) and estimated trade volumes (t per day).
PORT_METRICS = {
    "portcalls": "port calls, all vessels",
    "portcalls_tanker": "port calls, tankers",
    "portcalls_container": "port calls, container ships",
    "import": "import volume (t)",
    "export": "export volume (t)",
}

CARGO_TYPES = {
    "tanker": "tankers (crude oil, products, chemicals, LNG/LPG)",
    "dry_bulk": "dry bulk (ore, coal, grain)",
    "container": "containers (manufactured goods, also bagged polymers)",
    "general_cargo": "general cargo",
    "roro": "RoRo (vehicles)",
}

EVENT_TYPES = {
    "DR": "drought",
    "EQ": "earthquake",
    "FL": "flood",
    "OT": "other (e.g. conflict)",
    "TC": "tropical cyclone",
    "VO": "volcano",
    "WF": "wildfire",
}
