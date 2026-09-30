#!/usr/bin/env python3
"""
Read CrudeMaps features straight from an OSM .pbf extract (e.g. Geofabrik's
california-YYMMDD.osm.pbf) instead of Overpass. Needed for anything bigger than
a town: Overpass rate-limits long before a state is done.

Yields the same (cls, name, [(lat, lon), ...]) tuples as gen_tiles'
features_from_overpass, from the same tag set:
  natural=coastline, natural=water, waterway=river|canal, highway~<roads>
plus the member ways of natural=water multipolygon relations (big lakes and
river areas are relations whose ways carry no tags; Overpass `way[...]`
queries miss them).

Requires pyosmium (not in the stdlib):
  python3 -m venv tools/.venv && tools/.venv/bin/pip install osmium
"""

import re

import osmium

import gen_tiles as gt


def _water_relation_members(path):
    """Pass 1: way id -> relation name (or None) for every member way of a
    natural=water multipolygon relation. Only the first outer member carries
    the name so each lake is labelled once."""
    members = {}
    fp = osmium.FileProcessor(path, osmium.osm.RELATION) \
        .with_filter(osmium.filter.TagFilter(("natural", "water")))
    for rel in fp:
        if rel.tags.get("type") != "multipolygon":
            continue
        name = rel.tags.get("name")
        for m in rel.members:
            if m.type != "w":
                continue
            members.setdefault(m.ref, None)
            if name and m.role == "outer":
                members[m.ref] = name
                name = None
    return members


def features_from_pbf(path, roads, bbox=None, log=print):
    """Pass 2: stream matching ways with node locations. `bbox` (S, W, N, E)
    keeps only ways with at least one node inside it, like Overpass does."""
    # Unanchored, like Overpass `highway~"..."` (so "trunk" also matches trunk_link).
    road_re = re.compile(roads)
    rel_members = _water_relation_members(path)
    log(f"  water-relation member ways: {len(rel_members)}")
    if bbox:
        s, w, n, e = bbox

    # Nodes must be read to fill the location cache; the entity filter then
    # drops them in C++ so the Python loop only sees ways.
    fp = osmium.FileProcessor(path, osmium.osm.NODE | osmium.osm.WAY) \
        .with_locations() \
        .with_filter(osmium.filter.EntityFilter(osmium.osm.WAY))
    for way in fp:
        tags = way.tags
        cls = None
        name = None
        if tags.get("natural") == "coastline":
            cls = gt.CLS_COAST
        elif tags.get("natural") == "water" or \
                tags.get("waterway") in ("river", "canal"):
            cls = gt.CLS_WATER
        elif road_re.search(tags.get("highway", "")):
            cls = gt.CLS_ROAD
        elif way.id in rel_members:
            cls = gt.CLS_WATER
            name = rel_members[way.id]
        if cls is None:
            continue
        if name is None:
            name = tags.get("name")
        try:
            pts = [(nd.lat, nd.lon) for nd in way.nodes]
        except osmium.InvalidLocationError:
            # Node clipped out of the extract: keep the part we have.
            pts = [(nd.lat, nd.lon) for nd in way.nodes if nd.location.valid()]
        if len(pts) < 2:
            continue
        if bbox and not any(s <= la <= n and w <= lo <= e for la, lo in pts):
            continue
        yield cls, name, pts
