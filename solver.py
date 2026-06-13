# -*- coding: utf-8 -*-
"""perfwire solver v3 — 物理寸法・EE制約・しきい値設定（perfwire_config.json）対応
処理: 1) ロックされていない部品を制約つき貪欲再配置（本体フットプリント・スパン・デカップリング近接・
        ネットクラス分離を考慮し、足が同ネットに隣接=ブリッジ化を最大化）
      2) ネットごとの連結成分を被覆線で接続（隣の空き穴＋ブリッジ、空き無し→直付け）
      3) EE監査（デカップリング距離 / 配線長クラス上限 / 高Z隣接 / パッド接合数 / 本体重なり）
usage: python solver.py <state.json> [--propose] [--config cfg.json] [-o out.json]
"""
import json
import sys
import io
import os
import math

DEF_CFG = {
    "grid_pitch_mm": 2.54,
    "physical": {
        "r": {"body_len_mm": 6.5, "body_wid_mm": 2.5, "bend_margin_mm": 0.3, "max_span_mm": 13.0,
              "diag": True, "standing": True, "standing_span_holes": [1, 2], "tall": False},
        "film": {"body_len_mm": 10.0, "body_wid_mm": 4.5, "pitch_holes": [2, 2], "diag": False, "tall": True},
        "disc": {"body_len_mm": 5.0, "body_wid_mm": 2.5, "pitch_holes": [1, 3], "diag": True, "tall": True},
        "elec": {"dia_mm": 6.5, "pitch_holes": [1, 3], "diag": True, "tall": True},
    },
    "rules": {"body_overlap": False, "max_joints_per_pad": 3, "edge_margin_holes": 0},
    "net_classes": {},
    "decoupling": [],
    "weights": {"bridge_bonus": 8, "wire_len": 1.0, "caution_base": 1.5, "hiz_mult": 3.0, "keep_away_penalty": 6.0},
    "propose_order": [],
}

def load_cfg(path):
    cfg = json.loads(json.dumps(DEF_CFG))
    if path and os.path.exists(path):
        user = json.load(io.open(path, encoding="utf-8"))
        def merge(a, b):
            for k, v in b.items():
                if isinstance(v, dict) and isinstance(a.get(k), dict):
                    merge(a[k], v)
                else:
                    a[k] = v
        merge(cfg, user)
    return cfg

def neighbors(p):
    return [(p[0] + 1, p[1]), (p[0] - 1, p[1]), (p[0], p[1] + 1), (p[0], p[1] - 1)]

def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

def footprint(kind, a, b, cfg, standing=False, pid=None):
    """本体が覆うセル集合（足の穴を除く）と tall フラグ。part_overrides で個体別寸法を上書き可"""
    P = dict(cfg["physical"][kind])
    if pid and cfg.get("part_overrides", {}).get(pid):
        P.update(cfg["part_overrides"][pid])
    pitch = cfg["grid_pitch_mm"]
    tall = bool(P.get("tall")) or standing
    cells = set()
    if kind == "elec":
        cx, cy = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        rad = P["dia_mm"] / 2.0
        for c in range(int(math.floor(cx - 2)), int(math.ceil(cx + 3))):
            for r in range(int(math.floor(cy - 2)), int(math.ceil(cy + 3))):
                if math.hypot((c - cx) * pitch, (r - cy) * pitch) < rad - 0.05:
                    cells.add((c, r))
    elif not standing:
        n = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
        for i in range(1, n):
            cells.add((round(a[0] + (b[0] - a[0]) * i / n), round(a[1] + (b[1] - a[1]) * i / n)))
    cells.discard(tuple(a))
    cells.discard(tuple(b))
    return cells, tall

def spans(kind, cfg):
    """許容スパン (dx,dy,standing) — 物理寸法から導出"""
    P = cfg["physical"][kind]
    pitch = cfg["grid_pitch_mm"]
    out = []
    if "pitch_holes" in P:
        lo, hi = P["pitch_holes"]
        for dx in range(-hi, hi + 1):
            for dy in range(-hi, hi + 1):
                if (dx, dy) == (0, 0):
                    continue
                if not P.get("diag") and dx != 0 and dy != 0:
                    continue
                d = math.hypot(dx, dy)
                if lo - 0.01 <= d <= hi + 0.01:
                    out.append((dx, dy, False))
    else:
        mn = P["body_len_mm"] + 2 * P.get("bend_margin_mm", 0.3)
        mx = P.get("max_span_mm", 13.0)
        for dx in range(-6, 7):
            for dy in range(-6, 7):
                if (dx, dy) == (0, 0):
                    continue
                if not P.get("diag", True) and dx != 0 and dy != 0:
                    continue
                d = math.hypot(dx, dy) * pitch
                if mn - 0.01 <= d <= mx + 0.01:
                    out.append((dx, dy, False))
        if P.get("standing"):
            slo, shi = P.get("standing_span_holes", [1, 2])
            for dx in range(-shi, shi + 1):
                for dy in range(-shi, shi + 1):
                    if (dx == 0) == (dy == 0):
                        continue
                    d = math.hypot(dx, dy)
                    if slo - 0.01 <= d <= shi + 0.01:
                        out.append((dx, dy, True))
    return out

class Board:
    def __init__(self, state, cfg):
        self.cfg = cfg
        self.cols = state["grid"]["cols"]
        self.rows = state["grid"]["rows"]
        self.blocked = {tuple(h) for h in state.get("blockedHoles", [])}
        self.net_of_lead = {k: v["net"] for k, v in state["leads"].items()}
        self.parts = json.loads(json.dumps(state["parts"]))
        self.state = state
        self.cls_of_net = {}
        for cname, cdef in cfg.get("net_classes", {}).items():
            for n in cdef.get("nets", []):
                self.cls_of_net[n] = cname
        self.rebuild()

    def rebuild(self):
        self.lead_pos, self.ic_block, self.body, self.overlaps = {}, set(), {}, []
        for p in self.parts:
            if p["kind"] == "ic":
                pins = {k: tuple(v) for k, v in p["pins"].items()}
                for k, xyv in pins.items():
                    self.lead_pos[p["id"] + "." + k] = xyv
                xs = sorted({v[0] for v in pins.values()})
                ys = sorted({v[1] for v in pins.values()})
                cells = set()
                for c in range(xs[0], xs[-1] + 1):
                    for r in range(ys[0], ys[-1] + 1):
                        if (c, r) not in pins.values():
                            cells.add((c, r))
                self.ic_block |= cells
                self.body[p["id"]] = (cells, True)
            else:
                names = p.get("leadNames") or [p["id"] + ".a", p["id"] + ".b"]
                a, b = tuple(p["leads"][0]), tuple(p["leads"][1])
                self.lead_pos[names[0]], self.lead_pos[names[1]] = a, b
                self.body[p["id"]] = footprint(p["kind"], a, b, self.cfg, p.get("standing", False), p["id"])
        for k, v in self.state["leads"].items():
            if k not in self.lead_pos:
                self.lead_pos[k] = tuple(v["at"])
        self.occupied = set(self.lead_pos.values())
        ids = list(self.body.keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                ov = self.body[ids[i]][0] & self.body[ids[j]][0]
                if ov and not self.cfg["rules"].get("body_overlap"):
                    sev = "ng" if (self.body[ids[i]][1] and self.body[ids[j]][1]) else "warn"
                    self.overlaps.append({"a": ids[i], "b": ids[j], "cells": sorted([list(x) for x in ov]), "sev": sev})
        self.body_cells = set()
        for pid, (cells, _t) in self.body.items():
            self.body_cells |= cells
        for pid, (cells, tall) in self.body.items():
            bad = cells & self.occupied
            for h in bad:
                self.overlaps.append({"a": pid, "b": "lead@" + str(h), "cells": [list(h)], "sev": "ng" if tall else "warn"})

    def inb(self, p):
        m = self.cfg["rules"].get("edge_margin_holes", 0)
        return 1 + m <= p[0] <= self.cols - m and 1 + m <= p[1] <= self.rows - m

    def usable(self, p):
        return self.inb(p) and p not in self.occupied and p not in self.blocked and p not in self.body_cells and p not in self.ic_block

    def cls(self, net):
        return self.cls_of_net.get(net)

    def cdef(self, net):
        return self.cfg["net_classes"].get(self.cls(net), {})

def part_lead_names(p):
    if p["kind"] == "ic":
        return [p["id"] + "." + k for k in p["pins"]]
    return p.get("leadNames") or [p["id"] + ".a", p["id"] + ".b"]

def erc_audit(bd, net_of_hole, pad_bridges, wires, cfg):
    """ネットリスト/トポロジ系の電気ルールチェック（ERC）と設計レビュー系の監査。
    すべて状態グラフ（leads / parts / padBridges / wires / net_classes）から計算する。
    任意設定（rail_rank / power_entry / rules.single_lead_allowlist）があれば該当チェックが有効化される。
    """
    out = {}
    leads_per_net = {}
    for lead, net in bd.net_of_lead.items():
        if net:
            leads_per_net.setdefault(net, []).append(lead)
    nets = sorted(leads_per_net.keys())

    # ERC: 部品の足でネット未割当のもの（フローティング端子）
    unconnected = []
    for p in bd.parts:
        for nm in part_lead_names(p):
            if not bd.net_of_lead.get(nm):
                unconnected.append(nm)
    out["unconnectedLeads"] = sorted(unconnected)

    # ERC: 単一リードネット（接続先が無い＝結線漏れ/タイポ）。任意の許可リストで I/O 点を除外
    allow = set(cfg.get("rules", {}).get("single_lead_allowlist", []))
    out["singleLeadNets"] = sorted([n for n, ls in leads_per_net.items() if len(ls) == 1 and n not in allow])

    # ERC: オープンネット（leads+padBridges+wires をたどっても 1 連結にならないネット）
    par = {}
    def f(x):
        par.setdefault(x, x)
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    def u(a, b):
        par[f(a)] = f(b)
    node_net = {}
    for lead, xyv in bd.lead_pos.items():
        node_net[xyv] = bd.net_of_lead.get(lead)
        f(xyv)
    for br in pad_bridges:
        a, b = tuple(br[0]), tuple(br[1])
        u(a, b)
    for w in wires:
        pts = []
        for e in (w["a"], w["b"]):
            h = tuple(e["pad"]) if e.get("direct") else tuple(e["hole"])
            node_net.setdefault(h, w["net"])
            pts.append(h)
            if not e.get("direct") and e.get("bridgeTo"):
                u(h, tuple(e["bridgeTo"]))
        u(pts[0], pts[1])
    roots_per_net = {}
    for node, net in node_net.items():
        if net:
            roots_per_net.setdefault(net, set()).add(f(node))
    out["openNets"] = sorted([n for n, rs in roots_per_net.items() if len(rs) > 1])

    # ERC: 重複 refdes（id 重複は leadNames/decoupling 参照を壊す）
    cnt = {}
    for p in bd.parts:
        cnt[p["id"]] = cnt.get(p["id"], 0) + 1
    out["duplicateIds"] = sorted([i for i, c in cnt.items() if c > 1])

    # ネット衛生: クラス未割当（cdef が空＝全 EE クラスルールを素通り）
    out["unclassifiedNets"] = sorted([n for n in nets if bd.cls(n) is None])

    # 信号: keep-away 違反の事後監査（配置スコアだけでなく結果も検査）。違反ホール単位に集約
    holes = sorted(net_of_hole.items())
    ka_viol = []
    for h, n in holes:
        cd = bd.cdef(n)
        ka, kh = cd.get("keep_away_from", []), cd.get("keep_away_holes", 0)
        if not ka or kh <= 0:
            continue
        near = []
        for h2, n2 in holes:
            if n2 == n or bd.cls(n2) not in ka:
                continue
            d = max(abs(h[0] - h2[0]), abs(h[1] - h2[1]))
            if d <= kh:
                near.append((d, n2, h2))
        if near:
            near.sort()
            d0, n0, h0 = near[0]
            ka_viol.append({"net": n, "hole": list(h), "nearestNet": n0, "nearestHole": list(h0), "d": d0, "count": len(near)})
    out["keepAway"] = ka_viol

    # 短絡注意: 8 近傍（対角含む）の異ネット隣接（はんだブリッジ厳禁箇所）。情報レベル
    shorts = []
    deltas = [(1, 0), (0, 1), (1, 1), (1, -1)]
    nh = dict(net_of_hole)
    for h, n in sorted(nh.items()):
        for dx, dy in deltas:
            q = (h[0] + dx, h[1] + dy)
            if q in nh and nh[q] != n:
                ortho = (dx == 0 or dy == 0)
                hiz = bd.cls(n) == "HIZ" or bd.cls(nh[q]) == "HIZ"
                shorts.append({"a": list(h), "b": list(q), "net1": n, "net2": nh[q],
                               "adj": "ortho" if ortho else "diag", "hiz": hiz})
    out["shortCautions"] = shorts

    # 極性: 電解の + 足がより高電位レールにあるか（任意 rail_rank。無ければ INFO）
    rank = cfg.get("rail_rank", {})
    pol = []
    for p in bd.parts:
        if p["kind"] != "elec" or "plus" not in p:
            continue
        names = part_lead_names(p)
        pi = p["plus"]
        pn, mn = bd.net_of_lead.get(names[pi]), bd.net_of_lead.get(names[1 - pi])
        if pn in rank and mn in rank:
            pol.append({"part": p["id"], "plusNet": pn, "minusNet": mn, "ok": rank[pn] > rank[mn]})
        else:
            pol.append({"part": p["id"], "plusNet": pn, "minusNet": mn, "ok": None})
    out["polarity"] = pol

    # 電源到達性: 各 PWR ネットが 1 連結かつ給電リードに根を持つか（任意 power_entry。無ければ空）
    pe = cfg.get("power_entry", {})
    preach = []
    for net, entry_leads in pe.items():
        roots = roots_per_net.get(net, set())
        entry_pos = [bd.lead_pos[l] for l in entry_leads if l in bd.lead_pos]
        rooted = any(f(p2) in roots for p2 in entry_pos)
        preach.append({"net": net, "components": len(roots), "hasEntry": bool(entry_pos),
                       "ok": len(roots) <= 1 and rooted})
    out["powerReach"] = preach

    # デカップリング充足: IC の電源ピン（PWR クラス、最低電位レール＝リターンを除く）が
    # decoupling リストに載っているか（存在チェック。距離は ee.decoupling が担当）
    listed = {d["pin"] for d in cfg.get("decoupling", [])}
    pwr_nets = set(cfg.get("net_classes", {}).get("PWR", {}).get("nets", []))
    supply_net = None
    if rank:
        ranked = [(rank[n], n) for n in pwr_nets if n in rank]
        if ranked:
            supply_net = max(ranked)[1]  # 正電源レール（最上位電位）の IC ピンのみが per-IC バイパスを要する
    cov = []
    for p in bd.parts:
        if p["kind"] != "ic":
            continue
        for pin in p["pins"]:
            nm = p["id"] + "." + pin
            net = bd.net_of_lead.get(nm)
            if (supply_net and net == supply_net) or (not supply_net and net in pwr_nets):
                cov.append({"pin": nm, "net": net, "covered": nm in listed})
    out["decouplingCoverage"] = cov
    return out

def _seg_gap(a, b, c, d):
    """2 線分 ab, cd の最短距離（端点ベース近似）。被覆線の実経路は不問＝端点直線で評価"""
    def pt_seg(p, s, e):
        sx, sy, ex, ey = s[0], s[1], e[0], e[1]
        dx, dy = ex - sx, ey - sy
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - sx) * dx + (p[1] - sy) * dy) / L))
        return math.hypot(p[0] - (sx + dx * t), p[1] - (sy + dy * t))
    return min(pt_seg(a, c, d), pt_seg(b, c, d), pt_seg(c, a, b), pt_seg(d, a, b))

def topology_audit(bd, net_of_hole, pad_bridges, wires, cfg):
    """ロードマップ EE: スター/デイジーGND トポロジ評価・高Zガード助言・平行配線クロストーク（端点近似）。"""
    out = {"grounding": [], "guard": [], "crosstalk": []}
    # ネットごとの隣接グラフ（padBridges + wires + bridgeTo）
    adj = {}
    def link(a, b):
        a, b = tuple(a), tuple(b)
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    for br in pad_bridges:
        link(br[0], br[1])
    for w in wires:
        ea = tuple(w["a"]["pad"] if w["a"].get("direct") else w["a"]["hole"])
        eb = tuple(w["b"]["pad"] if w["b"].get("direct") else w["b"]["hole"])
        link(ea, eb)
        for e in (w["a"], w["b"]):
            if not e.get("direct") and e.get("bridgeTo"):
                link(tuple(e["hole"]), tuple(e["bridgeTo"]))

    # スターGND / デイジーチェーン評価（power_entry を根に BFS）
    pe = cfg.get("power_entry", {})
    return_net = None
    rank = cfg.get("rail_rank", {})
    pwr_nets = set(cfg.get("net_classes", {}).get("PWR", {}).get("nets", []))
    if rank:
        ranked = [(rank[n], n) for n in pwr_nets if n in rank]
        if ranked:
            return_net = min(ranked)[1]  # 最低電位＝リターン（GND）
    for net, entry_leads in pe.items():
        roots = [bd.lead_pos[l] for l in entry_leads if l in bd.lead_pos]
        nodes = [h for h, n in net_of_hole.items() if n == net]
        if not roots or len(nodes) < 3:
            continue
        depth, seen, frontier, d = {}, set(), [tuple(r) for r in roots], 0
        for r in frontier:
            seen.add(r)
            depth[r] = 0
        while frontier:
            nxt = []
            d += 1
            for u in frontier:
                for v in adj.get(u, ()):
                    if net_of_hole.get(v) == net and v not in seen:
                        seen.add(v)
                        depth[v] = d
                        nxt.append(v)
            frontier = nxt
        reached = len(seen)
        max_depth = max(depth.values()) if depth else 0
        root_deg = sum(1 for r in roots for v in adj.get(tuple(r), ()) if net_of_hole.get(v) == net)
        # デイジーチェーン指標: 経路長が長く分岐が少ない＝共通インピーダンス結合リスク
        topo = "star" if max_depth <= 2 else ("daisy-chain" if max_depth >= max(4, reached * 0.6) else "mixed")
        daisy = topo == "daisy-chain" and net == return_net
        out["grounding"].append({"net": net, "rootDegree": root_deg, "reached": reached,
                                 "maxDepth": max_depth, "topology": topo, "daisyReturn": daisy})

    # 高Zガード助言（HIZ ノードの露出辺。実際のガード電位はバッファ出力＝設計判断）
    for net in sorted({n for n in bd.net_of_lead.values() if n}):
        if bd.cls(net) != "HIZ":
            continue
        hs = sorted([h for h, n in net_of_hole.items() if n == net])
        exposed = 0
        for h in hs:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    q = (h[0] + dx, h[1] + dy)
                    if net_of_hole.get(q) != net and bd.inb(q):
                        exposed += 1
        out["guard"].append({"net": net, "holes": [list(h) for h in hs], "exposedSides": exposed,
                             "note": "高Zノード。隣接の空き/異ネット辺をガード電位（通常はバッファ出力など低Z同電位）で囲うとリーク/結合を低減"})

    # クロストーク（端点近似）: 異ネットの被覆線が平行かつ近接、片方が HIZ/SIG
    sens = {"HIZ", "SIG"}
    segs = []
    for w in wires:
        a = tuple(w["a"]["pad"] if w["a"].get("direct") else w["a"]["hole"])
        b = tuple(w["b"]["pad"] if w["b"].get("direct") else w["b"]["hole"])
        if dist(a, b) >= 1.5:
            segs.append((w["net"], a, b))
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            n1, a1, b1 = segs[i]
            n2, a2, b2 = segs[j]
            if n1 == n2 or not ({bd.cls(n1), bd.cls(n2)} & sens):
                continue
            v1 = (b1[0] - a1[0], b1[1] - a1[1])
            v2 = (b2[0] - a2[0], b2[1] - a2[1])
            cross = abs(v1[0] * v2[1] - v1[1] * v2[0])
            mag = math.hypot(*v1) * math.hypot(*v2)
            if mag == 0:
                continue
            sin_ang = cross / mag  # 0=平行
            gap = _seg_gap(a1, b1, a2, b2)
            if sin_ang < 0.35 and gap < 2.0:
                out["crosstalk"].append({"netA": n1, "netB": n2, "gap": round(gap, 1),
                                         "hiz": bd.cls(n1) == "HIZ" or bd.cls(n2) == "HIZ"})
    return out

def solve(state, cfg, propose=False):
    bd = Board(state, cfg)
    W = cfg["weights"]
    decoup = {d["cap"]: d for d in cfg.get("decoupling", [])}

    if propose:
        movable = [p for p in bd.parts if p["kind"] != "ic" and not p.get("locked")]
        fixed_ids = {p["id"] for p in bd.parts if p.get("locked") or p["kind"] == "ic"}
        placed = {}
        for lead, xyv in bd.lead_pos.items():
            pid = lead.split(".")[0]
            if pid in fixed_ids or pid.startswith("W"):
                placed.setdefault(bd.net_of_lead.get(lead), set()).add(xyv)
        order = cfg.get("propose_order") or []
        movable.sort(key=lambda p: order.index(p["id"]) if p["id"] in order else 99)
        for p in movable:
            names = p.get("leadNames") or [p["id"] + ".a", p["id"] + ".b"]
            for nm in names:
                bd.occupied.discard(bd.lead_pos[nm])
            bd.body[p["id"]] = (set(), False)
            bd.rebuild_body_cells = None
        bd.body_cells = set()
        for pid, (cells, _t) in bd.body.items():
            bd.body_cells |= cells
        hiz_leads = []
        for p in movable:
            names = p.get("leadNames") or [p["id"] + ".a", p["id"] + ".b"]
            n1, n2 = bd.net_of_lead.get(names[0]), bd.net_of_lead.get(names[1])
            if n1 is None or n2 is None:  # 未接続の足を持つ部品は再配置対象外（ERC で報告）
                continue
            dec = decoup.get(p["id"])
            anchor = None
            if dec and dec.get("pin") in bd.lead_pos:
                anchor = bd.lead_pos[dec["pin"]]
                anchor_net = bd.net_of_lead.get(dec["pin"])
            best = None
            for c in range(1, bd.cols + 1):
                for r in range(1, bd.rows + 1):
                    p1 = (c, r)
                    if not bd.usable(p1):
                        continue
                    for dx, dy, standing in spans(p["kind"], cfg):
                        p2 = (c + dx, r + dy)
                        if not bd.usable(p2):
                            continue
                        cells, _tall = footprint(p["kind"], p1, p2, cfg, standing, p["id"])
                        if cells & (bd.occupied | bd.body_cells | bd.ic_block | bd.blocked):
                            continue
                        bad = False
                        if anchor is not None:
                            dl = p1 if bd.net_of_lead.get(names[0]) == anchor_net else p2
                            ddec = max(abs(dl[0] - anchor[0]), abs(dl[1] - anchor[1]))
                            if ddec > dec["max_holes"]:
                                continue
                        s = 0.0
                        for q, nn in ((p1, n1), (p2, n2)):
                            nodes = placed.get(nn)
                            if nodes:
                                if any(nb in nodes for nb in neighbors(q)):
                                    s -= W["bridge_bonus"]
                                else:
                                    s += W["wire_len"] * min(dist(q, m) for m in nodes)
                            cd = bd.cdef(nn)
                            ka, kh = cd.get("keep_away_from", []), cd.get("keep_away_holes", 0)
                            for on, ons in placed.items():
                                ocl = bd.cls(on)
                                for m in ons:
                                    md = max(abs(q[0] - m[0]), abs(q[1] - m[1]))
                                    if md == 1 and on != nn:
                                        pen = max(bd.cdef(nn).get("adj_penalty", 1), bd.cdef(on).get("adj_penalty", 1)) * W["caution_base"]
                                        if bd.cls(nn) == "HIZ" or ocl == "HIZ":
                                            pen *= W["hiz_mult"]
                                        s += pen
                                    if ocl in ka and md <= kh and on != nn:
                                        s += W["keep_away_penalty"]
                        if standing:
                            s += 0.5
                        if best is None or s < best[0]:
                            best = (s, p1, p2, standing)
            if best is None:
                continue
            _s, p1, p2, standing = best
            p["leads"] = [list(p1), list(p2)]
            if standing:
                p["standing"] = True
            bd.occupied |= {p1, p2}
            cells, _t = footprint(p["kind"], p1, p2, cfg, standing, p["id"])
            bd.body[p["id"]] = (cells, _t)
            bd.body_cells |= cells
            placed.setdefault(n1, set()).add(p1)
            placed.setdefault(n2, set()).add(p2)
        bd.rebuild()

    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        parent[find(a)] = find(b)

    net_of_hole = {}
    for lead, xyv in bd.lead_pos.items():
        net = bd.net_of_lead.get(lead)  # ネット未割当の足（ERC unconnectedLeads が報告）はスキップして監査を継続
        if net is None:
            continue
        net_of_hole[xyv] = net
        find(xyv)
    pad_bridges = []
    for net in sorted({n for n in bd.net_of_lead.values() if n}):
        nodes = sorted([xyv for xyv, n in net_of_hole.items() if n == net])
        for a in nodes:
            for nb in neighbors(a):
                if nb in net_of_hole and net_of_hole[nb] == net and find(a) != find(nb):
                    pad_bridges.append([list(a), list(nb)])
                    union(a, nb)

    wires, warnings = [], []
    for net in sorted({n for n in bd.net_of_lead.values()}):
        while True:
            comps = {}
            for xyv, n in net_of_hole.items():
                if n == net:
                    comps.setdefault(find(xyv), []).append(xyv)
            groups = list(comps.values())
            if len(groups) <= 1:
                break
            groups.sort(key=len, reverse=True)
            main, rest = groups[0], groups[1:]
            tgt = min(rest, key=lambda g: min(dist(a, b) for a in g for b in main))
            pa, pb = min(((a, b) for a in tgt for b in main), key=lambda ab: dist(*ab))
            ends = []
            for grp, anchor2, other in ((tgt, pa, pb), (main, pb, pa)):
                cand = None
                for m in sorted(grp, key=lambda m2: dist(m2, anchor2)):
                    for nb in neighbors(m):
                        if bd.usable(nb) and nb not in net_of_hole:
                            pen = (0 if m == anchor2 else 10) + 0.05 * dist(nb, other)
                            if cand is None or pen < cand[0]:
                                cand = (pen, nb, m)
                if cand is None:
                    ends.append({"tap": None, "pad": list(anchor2), "hole": list(anchor2), "direct": True})
                    warnings.append(f"{net}: {anchor2} 直付け")
                else:
                    _pen, hole, member = cand
                    ends.append({"tap": None, "pad": list(anchor2), "hole": list(hole), "bridgeTo": list(member), "direct": False})
                    net_of_hole[hole] = net
                    bd.occupied.add(hole)
                    find(hole)
                    union(hole, member)
            tapmap = {tuple(v): k for k, v in bd.lead_pos.items()}
            for e in ends:
                e["tap"] = tapmap.get(tuple(e["pad"]), net)
            union(tuple(ends[0]["hole"]), tuple(ends[1]["hole"]))
            wlen = dist(ends[0]["hole"], ends[1]["hole"])
            mx = bd.cdef(net).get("max_wire_holes", 99)
            if wlen > mx:
                warnings.append(f"{net}: 配線長 {wlen:.1f} 穴 > クラス上限 {mx}")
            wires.append({"net": net, "a": ends[0], "b": ends[1]})

    cautions = []
    for xyv, n1 in sorted(net_of_hole.items()):
        for d in [(1, 0), (0, 1)]:
            q = (xyv[0] + d[0], xyv[1] + d[1])
            if q in net_of_hole and net_of_hole[q] != n1:
                cautions.append([list(xyv), list(q), n1, net_of_hole[q]])

    ee = {"decoupling": [], "hizCautions": [], "padJoints": [], "bodyOverlaps": bd.overlaps, "wireLength": []}
    for d in cfg.get("decoupling", []):
        cap, pin = d["cap"], d["pin"]
        cpart = next((p for p in bd.parts if p["id"] == cap), None)
        if not cpart or pin not in bd.lead_pos:
            continue
        anet = bd.net_of_lead.get(pin)
        names = cpart.get("leadNames") or []
        lead = next((nm for nm in names if bd.net_of_lead.get(nm) == anet), None)
        if not lead:
            continue
        lp, ap = bd.lead_pos[lead], bd.lead_pos[pin]
        dd = max(abs(lp[0] - ap[0]), abs(lp[1] - ap[1]))
        ee["decoupling"].append({"cap": cap, "pin": pin, "holes": dd, "max": d["max_holes"], "ok": dd <= d["max_holes"]})
    for c in cautions:
        if bd.cls(c[2]) == "HIZ" or bd.cls(c[3]) == "HIZ":
            ee["hizCautions"].append(c)
    joints = {}
    for b in pad_bridges:
        for h in (tuple(b[0]), tuple(b[1])):
            joints[h] = joints.get(h, 0) + 1
    for w in wires:
        for e in (w["a"], w["b"]):
            if not e["direct"] and e.get("bridgeTo"):
                joints[tuple(e["bridgeTo"])] = joints.get(tuple(e["bridgeTo"]), 0) + 1
    mxj = cfg["rules"].get("max_joints_per_pad", 3)
    for h, n in sorted(joints.items()):
        if n > mxj:
            ee["padJoints"].append({"hole": list(h), "joints": n, "max": mxj})
    for w in wires:
        wlen = dist(w["a"]["hole"], w["b"]["hole"])
        mx = bd.cdef(w["net"]).get("max_wire_holes", 99)
        ee["wireLength"].append({"net": w["net"], "holes": round(wlen, 1), "max": mx, "ok": wlen <= mx})

    ee.update(erc_audit(bd, net_of_hole, pad_bridges, wires, cfg))
    ee.update(topology_audit(bd, net_of_hole, pad_bridges, wires, cfg))

    ee_ng = (sum(1 for x in ee["decoupling"] if not x["ok"]) + len(ee["padJoints"])
             + sum(1 for o in bd.overlaps if o["sev"] == "ng")
             + sum(1 for x in ee["wireLength"] if not x["ok"])
             + len(ee["openNets"]) + len(ee["unconnectedLeads"]) + len(ee["duplicateIds"])
             + sum(1 for x in ee["polarity"] if x["ok"] is False)
             + sum(1 for x in ee["powerReach"] if not x["ok"]))
    ee_warn = (sum(1 for o in bd.overlaps if o["sev"] == "warn")
               + len(ee["singleLeadNets"]) + len(ee["keepAway"]) + len(ee["unclassifiedNets"])
               + sum(1 for g in ee["grounding"] if g["daisyReturn"]))

    out = json.loads(json.dumps(state))
    out["parts"] = bd.parts
    out["leads"] = {lead: {"net": bd.net_of_lead.get(lead), "at": list(xyv)} for lead, xyv in bd.lead_pos.items()}
    out["padBridges"] = pad_bridges
    out["wires"] = wires
    out["warnings"] = warnings
    out["cautions"] = cautions
    ee["fabReady"] = ee_ng == 0
    out["ee"] = ee
    out["stats"] = {"bridges": len(pad_bridges) + sum(1 for w in wires for e in (w["a"], w["b"]) if not e["direct"]),
                    "wires": len(wires),
                    "direct": sum(1 for w in wires for e in (w["a"], w["b"]) if e["direct"]),
                    "cautions": len(cautions),
                    "eeNg": ee_ng,
                    "eeWarn": ee_warn,
                    "fabReady": ee_ng == 0}
    return out

if __name__ == "__main__":
    src = sys.argv[1]
    propose = "--propose" in sys.argv
    cfgp = sys.argv[sys.argv.index("--config") + 1] if "--config" in sys.argv else os.path.join(os.path.dirname(os.path.abspath(__file__)), "perfwire_config.json")
    dst = sys.argv[sys.argv.index("-o") + 1] if "-o" in sys.argv else None
    cfg = load_cfg(cfgp)
    state = json.load(io.open(src, encoding="utf-8"))
    result = solve(state, cfg, propose=propose)
    print(("PROPOSE" if propose else "ALLOCATE"), json.dumps(result["stats"], ensure_ascii=False))
    e = result["ee"]
    print(" fabReady:", e["fabReady"])
    print(" EE decoupling:", json.dumps(e["decoupling"], ensure_ascii=False))
    bad = [x for x in e["wireLength"] if not x["ok"]]
    print(" EE wire-length NG:", json.dumps(bad, ensure_ascii=False))
    print(" EE hiZ cautions:", len(e["hizCautions"]), " padJoints NG:", len(e["padJoints"]),
          " bodyOverlaps:", len(e["bodyOverlaps"]))
    print(" ERC openNets:", json.dumps(e["openNets"], ensure_ascii=False),
          " unconnected:", json.dumps(e["unconnectedLeads"], ensure_ascii=False),
          " duplicateIds:", json.dumps(e["duplicateIds"], ensure_ascii=False))
    print(" ERC singleLeadNets:", json.dumps(e["singleLeadNets"], ensure_ascii=False),
          " unclassified:", json.dumps(e["unclassifiedNets"], ensure_ascii=False))
    polbad = [x for x in e["polarity"] if x["ok"] is False]
    preachbad = [x["net"] for x in e["powerReach"] if not x["ok"]]
    print(" EE polarity NG:", json.dumps(polbad, ensure_ascii=False),
          " powerReach NG:", json.dumps(preachbad, ensure_ascii=False),
          " keepAway viol:", len(e["keepAway"]),
          " decoupCoverage:", sum(1 for x in e["decouplingCoverage"] if x["covered"]), "/", len(e["decouplingCoverage"]))
    print(" GND topology:", json.dumps(e["grounding"], ensure_ascii=False),
          " guard(HIZ):", len(e["guard"]), " crosstalk pairs:", len(e["crosstalk"]))
    for w in result["warnings"]:
        print("  *", w)
    if dst:
        io.open(dst, "w", encoding="utf-8").write(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        print(" ->", dst)
