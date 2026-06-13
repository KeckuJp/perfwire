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
import re

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
        self.net_of_lead = {k: v.get("net") for k, v in state["leads"].items()}
        # 不正形状の部品（pins 欠落/空/非dict の IC、leads が list でない/2本未満の素子）は取り込み時に
        # 除外し、監査全体が例外で落ちないようにする（電気的実体が無いので報告対象も無い）。
        def _valid(p):
            if p.get("kind") == "ic":
                return isinstance(p.get("pins"), dict) and len(p["pins"]) > 0
            return isinstance(p.get("leads"), list) and len(p["leads"]) >= 2
        self.parts = [p for p in json.loads(json.dumps(state["parts"])) if _valid(p)]
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
                pins = {k: tuple(v) for k, v in (p.get("pins") or {}).items()}
                if not pins:
                    continue  # 不正形状（pins 欠落/空）は監査を止めず黙ってスキップ
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
                lds = p.get("leads")
                if not lds or len(lds) < 2:
                    continue  # 不正形状（leads 欠落）は監査を止めず黙ってスキップ（ERC が未接続として報告）
                names = p.get("leadNames") or [p["id"] + ".a", p["id"] + ".b"]
                a, b = tuple(lds[0]), tuple(lds[1])
                self.lead_pos[names[0]], self.lead_pos[names[1]] = a, b
                self.body[p["id"]] = footprint(p["kind"], a, b, self.cfg, p.get("standing", False), p["id"])
        for k, v in self.state["leads"].items():
            if k not in self.lead_pos and v.get("at"):
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

def strip_segments(cols, rows, axis, cutset):
    """ストリップボードの導通セグメント。各ストリップ（行 or 列）を track cut で分割した連続穴の並び。"""
    segs = []
    if axis == "col":
        for c in range(1, cols + 1):
            seg = [(c, 1)]
            for r in range(2, rows + 1):
                if frozenset(((c, r - 1), (c, r))) in cutset:
                    segs.append(seg)
                    seg = []
                seg.append((c, r))
            if seg:
                segs.append(seg)
    else:
        for r in range(1, rows + 1):
            seg = [(1, r)]
            for c in range(2, cols + 1):
                if frozenset(((c - 1, r), (c, r))) in cutset:
                    segs.append(seg)
                    seg = []
                seg.append((c, r))
            if seg:
                segs.append(seg)
    return segs

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
    # ストリップボード: 同一ストリップ（cut で分割した連続穴）は銅箔で連結。セグメント内を union し、
    # 同セグメントに異ネットのリードが乗っていれば確実なショート（要 track cut）= stripShorts。
    grid = bd.state.get("grid", {})
    strip_shorts = []
    if grid.get("type") == "strip":
        cutset = set()
        for cc in bd.state.get("trackCuts", []):
            cutset.add(frozenset((tuple(cc[0]), tuple(cc[1]))))
        for seg in strip_segments(bd.cols, bd.rows, grid.get("stripAxis", "row"), cutset):
            for i in range(1, len(seg)):
                u(seg[i - 1], seg[i])
            nets_on = sorted({node_net.get(h) for h in seg if node_net.get(h)})
            if len(nets_on) >= 2:
                strip_shorts.append({"segment": [list(seg[0]), list(seg[-1])], "nets": nets_on})
    out["stripShorts"] = strip_shorts
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
        if not isinstance(pi, int) or pi not in (0, 1) or len(names) < 2:
            pol.append({"part": p["id"], "plusNet": None, "minusNet": None, "ok": None})
            continue
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
        if net not in leads_per_net:
            continue  # この基板で未使用の電源ネットは対象外（config の powerEntry が他基板の名を含むケース）
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

    # 浮いた電源ピン: IC の電源ピン（PWR クラス）がそのネットに自分しか居ない＝給電未接続。製作阻止 NG
    floating = []
    for p in bd.parts:
        if p["kind"] != "ic":
            continue
        for pin in p["pins"]:
            nm = p["id"] + "." + pin
            net = bd.net_of_lead.get(nm)
            if net in pwr_nets and len(leads_per_net.get(net, [])) < 2:
                floating.append(nm)
    out["floatingPowerPins"] = sorted(floating)

    # 端子の電気的役割を解決（ICは part.pinTypes、任意で leads[name].role が上書き。R/C はパッシブ）。
    # ドライバ/負荷の所在を問わない＝外部MCU/電源が線で入る端子も leads[name].role で表現できる。
    role = {}
    for p in bd.parts:
        if p["kind"] == "ic":
            pt = p.get("pinTypes")
            pt = pt if isinstance(pt, dict) else {}
            for pin in p["pins"]:
                r = pt.get(pin)
                if r:
                    role[p["id"] + "." + pin] = r
        else:
            for nm in part_lead_names(p):
                role[nm] = "passive"
    for nm, L in bd.state["leads"].items():
        if L.get("role"):
            role[nm] = L["role"]
    # 出力-出力ショート（ドライバ衝突）: 同一ネットに role=out の端子が 2 本以上＝確実な競合。
    # oc/od/tri/bidir はワイヤードOR/バス共有が成立するため数えない。外部出力端子(W.*)も同列に数える。
    drivers = {}
    for nm, net in bd.net_of_lead.items():
        if net and role.get(nm) == "out":
            drivers.setdefault(net, []).append(nm)
    out["multipleDrivers"] = [{"net": n, "pins": sorted(ps)} for n, ps in sorted(drivers.items()) if len(ps) >= 2]

    # 未駆動ネット（フローティング入力）: そのネットの全リードが role=in（入力のみ・ドライバもパッシブも無い）。
    # 抵抗等(passive)でバイアスされた高Z入力(INA_P等)は passive リードを持つので除外＝誤検出回避。
    undriven = []  # 全リードが in（型付き入力のみ）＝ドライバ無し。未型付け(None)が混じる場合は保守的に非該当
    leads_role_per_net = {}
    for nm, net in bd.net_of_lead.items():
        if net:
            leads_role_per_net.setdefault(net, []).append(role.get(nm))
    for net, rs in sorted(leads_role_per_net.items()):
        if rs and all(r == "in" for r in rs):
            undriven.append(net)
    out["undrivenNets"] = undriven

    # 値考慮の EE 深化（すべて任意入力依存・後方互換）:
    rail_volts = cfg.get("rail_volts", {}) if isinstance(cfg.get("rail_volts"), dict) else {}
    # 抵抗の消費電力: 両端ネットの電位が rail_volts で既知なら P=ΔV^2/R。定格(rated_w 既定0.25W)超で NG。
    res_power = []
    for p in bd.parts:
        if p.get("kind") != "r":
            continue
        R = p.get("value")
        if not isinstance(R, (int, float)) or R <= 0:
            continue
        nm = p.get("leadNames") or [p["id"] + ".a", p["id"] + ".b"]
        n1, n2 = bd.net_of_lead.get(nm[0]), bd.net_of_lead.get(nm[1])
        if n1 in rail_volts and n2 in rail_volts:
            w = (rail_volts[n1] - rail_volts[n2]) ** 2 / R
            rated = p.get("rated_w", 0.25)
            res_power.append({"part": p["id"], "watts": round(w, 4), "rated": rated, "ok": w <= rated})
    out["resistorPower"] = res_power
    # デカップリング値の妥当性: バイパスに 1uF 超を割り当てていれば HF 不足の警告（0.01-0.1uF 推奨）。
    listed_caps = {d["cap"] for d in cfg.get("decoupling", [])}
    dec_val = []
    for p in bd.parts:
        if p["id"] in listed_caps and isinstance(p.get("value"), (int, float)) and p["value"] > 1e-6:
            dec_val.append({"cap": p["id"], "farads": p["value"]})
    out["decouplingValueWarn"] = dec_val
    # ピン競合: 同一ネットに out(論理出力) と pwr/pwr_out(電源源) = 出力を電源に短絡＝NG。
    roles_by_net = {}
    for nm2, net in bd.net_of_lead.items():
        r = role.get(nm2)
        if net and r:
            roles_by_net.setdefault(net, set()).add(r)
    pin_conflicts = []
    for net, rs in sorted(roles_by_net.items()):
        if "out" in rs and (rs & {"pwr", "pwr_out"}):
            pin_conflicts.append({"net": net, "kinds": sorted(rs)})
    out["pinConflicts"] = pin_conflicts
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
        ring = set()  # 具体的なガード穴候補（HIZ穴に隣接する空き穴。ここをガード電位で囲う）
        for h in hs:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    q = (h[0] + dx, h[1] + dy)
                    if net_of_hole.get(q) != net and bd.inb(q):
                        exposed += 1
                        if q not in net_of_hole and q not in bd.blocked and q not in bd.body_cells and q not in bd.ic_block:
                            ring.add(q)
        out["guard"].append({"net": net, "holes": [list(h) for h in hs], "exposedSides": exposed,
                             "ringHoles": sorted([list(q) for q in ring]),
                             "note": "高Zノード。ringHoles の空き穴をガード電位（通常はバッファ出力など低Z同電位）で囲うとリーク/結合を低減"})

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

def _hole_name(p):
    return str(p[0]) + chr(64 + p[1])

def cut_sheet(state, cfg):
    """各被覆線の物理切断長（端点間距離×ピッチ + 両端のリード余長）。経路は端点直線で近似。"""
    pitch = cfg.get("grid_pitch_mm", 2.54)
    margin = cfg.get("rules", {}).get("lead_margin_mm", 5.0)
    rows = []
    for w in state.get("wires", []):
        a = w["a"]["pad"] if w["a"].get("direct") else w["a"]["hole"]
        b = w["b"]["pad"] if w["b"].get("direct") else w["b"]["hole"]
        straight = math.hypot(a[0] - b[0], a[1] - b[1]) * pitch
        manhattan = (abs(a[0] - b[0]) + abs(a[1] - b[1])) * pitch
        rows.append({"net": w["net"], "from": _hole_name(a), "to": _hole_name(b),
                     "straight_mm": round(straight + 2 * margin, 1), "manhattan_mm": round(manhattan + 2 * margin, 1)})
    return rows

def bom_rows(state):
    """部品を kind+label でまとめた BOM。"""
    groups = {}
    for p in state.get("parts", []):
        key = (p.get("kind", "?"), p.get("label") or p.get("id", "?"))
        groups.setdefault(key, []).append(p.get("id", "?"))
    return [{"kind": k[0], "label": k[1], "qty": len(ids), "refs": sorted(ids)} for k, ids in sorted(groups.items())]

def build_packet_md(state, cfg):
    """ベンチ用ビルドパケット（BOM + 切断長表 + ブリッジ一覧）を markdown で。"""
    bom = bom_rows(state)
    cuts = cut_sheet(state, cfg)
    out = ["# perfwire build packet — " + str(state.get("proposal", "")), "",
           "## BOM (" + str(sum(b["qty"] for b in bom)) + " parts)", "",
           "| kind | label | qty | refs |", "|---|---|---|---|"]
    for b in bom:
        out.append("| " + b["kind"] + " | " + b["label"] + " | " + str(b["qty"]) + " | " + ", ".join(b["refs"]) + " |")
    out += ["", "## Jumper cut sheet (" + str(len(cuts)) + " wires; lead margin " + str(cfg.get("rules", {}).get("lead_margin_mm", 5.0)) + "mm each end)", "",
            "| net | from | to | straight mm | manhattan mm |", "|---|---|---|---|---|"]
    for c in cuts:
        out.append("| " + c["net"] + " | " + c["from"] + " | " + c["to"] + " | " + str(c["straight_mm"]) + " | " + str(c["manhattan_mm"]) + " |")
    br = state.get("padBridges", [])
    out += ["", "## Solder bridges (" + str(len(br)) + ")", ""]
    out += ["- " + _hole_name(b[0]) + " — " + _hole_name(b[1]) for b in br] or ["(none)"]
    return "\n".join(out) + "\n"

_PWR_NAMES = ("GND", "VSS", "VEE", "VCC", "VDD", "VMID", "VREF", "AGND", "DGND", "V3V3", "3V3", "5V", "1V8")

def _is_pwr(n):
    u = (n or "").upper()
    return u in _PWR_NAMES or bool(re.match(r"^[+\-]?\d+V\d*$", u)) or bool(re.match(r"^V\d+$", u))

def emit_config(state):
    """盤面状態から perfwire_config.json の叩き台を導出（ヒューリスティック）。人がレビュー前提。
    既存の DEF_CFG をベースに、推定できる net_classes / rail_rank / power_entry /
    single_lead_allowlist / decoupling を埋め、不確実な箇所は _TODO で印を付ける。"""
    leads = state.get("leads", {})
    parts = state.get("parts", [])
    role = {}
    for p in parts:
        if p.get("kind") == "ic":
            pt = p.get("pinTypes") if isinstance(p.get("pinTypes"), dict) else {}
            for pin in (p.get("pins") or {}):
                if pt.get(pin):
                    role[p["id"] + "." + pin] = pt[pin]
        else:
            for nm in (p.get("leadNames") or [p.get("id", "") + ".a", p.get("id", "") + ".b"]):
                role[nm] = "passive"
    for nm, v in leads.items():
        if v.get("role"):
            role[nm] = v["role"]
    lpn = {}
    for nm, v in leads.items():
        n = v.get("net")
        if n:
            lpn.setdefault(n, []).append(nm)
    nets = sorted(lpn)
    classes = {"HIZ": [], "SIG": [], "OUT": [], "PWR": []}
    for n in nets:
        if _is_pwr(n):
            classes["PWR"].append(n)
        elif any(role.get(l) == "out" for l in lpn[n]):
            classes["OUT"].append(n)
        else:
            classes["SIG"].append(n)
    rank = {}
    for n in classes["PWR"]:
        u = n.upper()
        rank[n] = 0 if any(x in u for x in ("GND", "VSS", "VEE", "AGND", "DGND")) else (1 if ("VMID" in u or "VREF" in u) else 2)
    pe = {n: [l for l in lpn[n] if l.startswith("W.")] for n in classes["PWR"] if any(l.startswith("W.") for l in lpn[n])}
    allow = [n for n in nets if len(lpn[n]) == 1]
    leadpos = {nm: tuple(v["at"]) for nm, v in leads.items() if v.get("at")}
    for p in parts:
        if p.get("kind") == "ic":
            for pin, xy in (p.get("pins") or {}).items():
                leadpos[p["id"] + "." + pin] = tuple(xy)
    decoup = []
    for p in parts:
        if p.get("kind") != "ic":
            continue
        for pin in (p.get("pins") or {}):
            nm = p["id"] + "." + pin
            net = leads.get(nm, {}).get("net")
            if not net or not _is_pwr(net) or rank.get(net, 2) == 0 or nm not in leadpos:
                continue
            best = None
            for q in parts:
                if q.get("kind") not in ("disc", "film", "elec"):
                    continue
                for ql in (q.get("leadNames") or []):
                    if leads.get(ql, {}).get("net") == net and ql in leadpos:
                        d = max(abs(leadpos[ql][0] - leadpos[nm][0]), abs(leadpos[ql][1] - leadpos[nm][1]))
                        if best is None or d < best[0]:
                            best = (d, q["id"])
            if best:
                decoup.append({"cap": best[1], "pin": nm, "max_holes": max(2, best[0])})
    cfg = json.loads(json.dumps(DEF_CFG))
    cfg["_comment"] = "perfwire_config draft from solver.py --emit-config. REVIEW: net classes are heuristic (PWR by name, OUT by role=out, rest SIG); mark high-Z nodes into HIZ; tune limits."
    cfg["net_classes"] = {
        "HIZ": {"_TODO": "move true high-impedance nodes (e.g. op-amp inputs) here", "nets": [], "max_wire_holes": 6, "adj_penalty": 8, "keep_away_from": ["OUT", "PWR"], "keep_away_holes": 2},
        "SIG": {"nets": classes["SIG"], "max_wire_holes": 14, "adj_penalty": 3, "keep_away_from": [], "keep_away_holes": 0},
        "OUT": {"nets": classes["OUT"], "max_wire_holes": 99, "adj_penalty": 2, "keep_away_from": ["HIZ"], "keep_away_holes": 2},
        "PWR": {"nets": classes["PWR"], "max_wire_holes": 99, "adj_penalty": 1, "keep_away_from": [], "keep_away_holes": 0},
    }
    cfg["rail_rank"] = rank
    cfg["power_entry"] = pe
    cfg["decoupling"] = decoup
    cfg.setdefault("rules", {})["single_lead_allowlist"] = allow
    cfg["rules"]["_single_lead_allowlist_TODO"] = "auto-listed single-lead nets (likely external I/O ports); remove any that are genuine wiring gaps"
    return cfg

def fix_suggestions(ee):
    """各監査指摘に機械可読な対処案を添える（advisory; 自動適用はしない）。"""
    fx = []
    for n in ee.get("openNets", []):
        fx_add = ("openNet", n, "ジャンパーで分断された島を接続 / connect the islands with a jumper")
        fx.append({"finding": fx_add[0], "target": fx_add[1], "suggestion": fx_add[2]})
    for s in ee.get("stripShorts", []):
        fx.append({"finding": "stripShort", "target": "/".join(s["nets"]), "suggestion": "セグメント " + str(s["segment"]) + " に track cut を入れて分離 / add a track cut to split"})
    for m in ee.get("multipleDrivers", []):
        fx.append({"finding": "multipleDrivers", "target": m["net"], "suggestion": "ドライバ " + ",".join(m["pins"]) + " の片方を外す / remove one driver"})
    for nm in ee.get("unconnectedLeads", []):
        fx.append({"finding": "unconnectedLead", "target": nm, "suggestion": "ネットを割り当てる / assign a net"})
    for i in ee.get("duplicateIds", []):
        fx.append({"finding": "duplicateId", "target": i, "suggestion": "一意の refdes に変更 / make the refdes unique"})
    for nm in ee.get("floatingPowerPins", []):
        fx.append({"finding": "floatingPowerPin", "target": nm, "suggestion": "電源レールに接続 / connect to the supply rail"})
    for p in ee.get("polarity", []):
        if p.get("ok") is False:
            fx.append({"finding": "polarity", "target": p["part"], "suggestion": "+ 足を高電位側へ / put the + lead on the higher rail"})
    for p in ee.get("powerReach", []):
        if not p.get("ok"):
            fx.append({"finding": "powerReach", "target": p["net"], "suggestion": "給電リードまで結線 / wire it back to the supply entry"})
    for d in ee.get("decoupling", []):
        if not d.get("ok"):
            fx.append({"finding": "decoupling", "target": d["cap"] + "->" + d["pin"], "suggestion": "パスコンをピンの " + str(d["max"]) + " 穴以内へ移動 / move the cap within " + str(d["max"]) + " holes"})
    for w in ee.get("wireLength", []):
        if not w.get("ok"):
            fx.append({"finding": "wireLength", "target": w["net"], "suggestion": "経路短縮または再配置 / shorten the run or re-place"})
    for c in ee.get("pinConflicts", []):
        fx.append({"finding": "pinConflict", "target": c["net"], "suggestion": "論理出力を電源レールから切り離す / separate the output from the power rail"})
    for r in ee.get("resistorPower", []):
        if not r.get("ok"):
            fx.append({"finding": "resistorPower", "target": r["part"], "suggestion": "定格Wを上げる or 抵抗値を見直す / increase rated W or revise R"})
    return fx

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
    for net in sorted({n for n in bd.net_of_lead.values() if n}):
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
             + sum(1 for x in ee["powerReach"] if not x["ok"]) + len(ee["floatingPowerPins"])
             + len(ee["multipleDrivers"]) + len(ee["stripShorts"])
             + sum(1 for x in ee["resistorPower"] if not x["ok"]) + len(ee["pinConflicts"]))
    ee_warn = (sum(1 for o in bd.overlaps if o["sev"] == "warn")
               + len(ee["singleLeadNets"]) + len(ee["keepAway"]) + len(ee["unclassifiedNets"])
               + sum(1 for g in ee["grounding"] if g["daisyReturn"]) + len(ee["undrivenNets"])
               + len(ee["decouplingValueWarn"]))

    out = json.loads(json.dumps(state))
    out["parts"] = bd.parts
    out["leads"] = {lead: {"net": bd.net_of_lead.get(lead), "at": list(xyv)} for lead, xyv in bd.lead_pos.items()}
    out["padBridges"] = pad_bridges
    out["wires"] = wires
    out["warnings"] = warnings
    out["cautions"] = cautions
    ee["fabReady"] = ee_ng == 0
    ee["fixes"] = fix_suggestions(ee)
    out["ee"] = ee
    out["stats"] = {"bridges": len(pad_bridges) + sum(1 for w in wires for e in (w["a"], w["b"]) if not e["direct"]),
                    "wires": len(wires),
                    "direct": sum(1 for w in wires for e in (w["a"], w["b"]) if e["direct"]),
                    "cautions": len(cautions),
                    "eeNg": ee_ng,
                    "eeWarn": ee_warn,
                    "fabReady": ee_ng == 0}
    return out

def _resolve_guard_net(state, hiz_net):
    """高Zネットを囲うガード電位を推定: その入力ピンを持つ IC の出力ピンのネット（バッファ出力）。"""
    for p in state.get("parts", []):
        if p.get("kind") != "ic":
            continue
        pins = p.get("pins") or {}
        pt = p.get("pinTypes") if isinstance(p.get("pinTypes"), dict) else {}
        if any(state["leads"].get(p["id"] + "." + pin, {}).get("net") == hiz_net and pt.get(pin) == "in" for pin in pins):
            for pin in pins:
                if pt.get(pin) == "out":
                    return state["leads"].get(p["id"] + "." + pin, {}).get("net")
    return None

def synthesize_guard(state, cfg, hiz_net, guard_net=None):
    """高Zノードのガードリングを合成: 露出する隣接空き穴をガード電位の足として追加した新 state を返す。
    自動適用はしない＝呼び出し側が案として採用。ガードネットは guard_net 引数 > config.guard_of > 推定。"""
    bd = Board(state, cfg)
    hiz_holes = [xy for lead, xy in bd.lead_pos.items() if bd.net_of_lead.get(lead) == hiz_net]
    if not hiz_holes:
        return None, {"error": "no holes on net " + str(hiz_net)}
    if guard_net is None:
        guard_net = (cfg.get("guard_of") or {}).get(hiz_net) or _resolve_guard_net(state, hiz_net)
    if not guard_net:
        return None, {"error": "could not resolve a guard net for " + str(hiz_net) + " (pass --guard-net or set config.guard_of)"}
    ring = set()
    for h in hiz_holes:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                q = (h[0] + dx, h[1] + dy)
                if bd.usable(q):
                    ring.add(q)
    new = json.loads(json.dumps(state))
    safe = re.sub(r"[^A-Za-z0-9]", "", str(hiz_net))
    for i, q in enumerate(sorted(ring)):
        new["leads"]["GRD_%s_%d" % (safe, i)] = {"net": guard_net, "at": [q[0], q[1]], "role": "passive"}
    new["proposal"] = "guard:" + str(hiz_net) + "→" + str(guard_net)
    return new, {"hiz": hiz_net, "guard": guard_net, "ringHoles": sorted([list(q) for q in ring]), "count": len(ring)}

def propose_multi(state, cfg):
    """複数候補スコアリング: 重み格子で再配置を回し、(eeNg, 被覆線数, 注意数) 最小の案を採用。決定的。"""
    grid = [(bb, wl) for bb in (10, 20, 30) for wl in (0.5, 1.0, 2.0)]
    best, scored = None, []
    for bb, wl in grid:
        c = json.loads(json.dumps(cfg))
        c.setdefault("weights", {})
        c["weights"]["bridge_bonus"] = bb
        c["weights"]["wire_len"] = wl
        r = solve(json.loads(json.dumps(state)), c, propose=True)
        s = r["stats"]
        score = (s["eeNg"], s["wires"], s["cautions"])
        scored.append({"bridge_bonus": bb, "wire_len": wl, "eeNg": s["eeNg"], "wires": s["wires"], "cautions": s["cautions"]})
        if best is None or score < best[0]:
            best = (score, r, (bb, wl))
    best[1]["proposeScores"] = scored
    best[1]["proposeBest"] = {"bridge_bonus": best[2][0], "wire_len": best[2][1], "eeNg": best[0][0], "wires": best[0][1]}
    return best[1]

if __name__ == "__main__":
    src = sys.argv[1]
    propose = "--propose" in sys.argv
    cfgp = sys.argv[sys.argv.index("--config") + 1] if "--config" in sys.argv else os.path.join(os.path.dirname(os.path.abspath(__file__)), "perfwire_config.json")
    dst = sys.argv[sys.argv.index("-o") + 1] if "-o" in sys.argv else None
    cfg = load_cfg(cfgp)
    state = json.load(io.open(src, encoding="utf-8"))
    if "--guard" in sys.argv:
        hiz = sys.argv[sys.argv.index("--guard") + 1]
        gn = sys.argv[sys.argv.index("--guard-net") + 1] if "--guard-net" in sys.argv else None
        targets = [n for n in cfg.get("net_classes", {}).get("HIZ", {}).get("nets", [])] if hiz == "all" else [hiz]
        cur = state
        info = []
        for t in targets:
            new, meta = synthesize_guard(cur, cfg, t, gn)
            info.append(meta)
            if new:
                cur = new
        sys.stderr.write("guard synthesis: " + json.dumps(info, ensure_ascii=False) + "\n")
        out = json.dumps(cur, ensure_ascii=False, separators=(",", ":"))
        (io.open(dst, "w", encoding="utf-8").write(out) if dst else sys.stdout.write(out + "\n"))
        sys.exit(0)
    if "--emit-config" in sys.argv:
        out = json.dumps(emit_config(state), ensure_ascii=False, indent=2)
        (io.open(dst, "w", encoding="utf-8").write(out) if dst else sys.stdout.write(out + "\n"))
        sys.exit(0)
    if "--emit-packet" in sys.argv:
        result = solve(state, cfg, propose=propose)
        md = build_packet_md(result, cfg)
        (io.open(dst, "w", encoding="utf-8").write(md) if dst else sys.stdout.write(md))
        sys.exit(0)
    if "--propose-n" in sys.argv:
        result = propose_multi(state, cfg)
        print("PROPOSE-N best", json.dumps(result["proposeBest"], ensure_ascii=False))
        print(" scores:", json.dumps(result["proposeScores"], ensure_ascii=False))
    else:
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
          " unclassified:", json.dumps(e["unclassifiedNets"], ensure_ascii=False),
          " floatingPowerPins:", json.dumps(e["floatingPowerPins"], ensure_ascii=False))
    polbad = [x for x in e["polarity"] if x["ok"] is False]
    preachbad = [x["net"] for x in e["powerReach"] if not x["ok"]]
    print(" EE polarity NG:", json.dumps(polbad, ensure_ascii=False),
          " powerReach NG:", json.dumps(preachbad, ensure_ascii=False),
          " keepAway viol:", len(e["keepAway"]),
          " decoupCoverage:", sum(1 for x in e["decouplingCoverage"] if x["covered"]), "/", len(e["decouplingCoverage"]))
    print(" GND topology:", json.dumps(e["grounding"], ensure_ascii=False),
          " guard(HIZ):", len(e["guard"]), " crosstalk pairs:", len(e["crosstalk"]))
    print(" multipleDrivers(out-out short):", json.dumps(e["multipleDrivers"], ensure_ascii=False),
          " undrivenNets:", json.dumps(e["undrivenNets"], ensure_ascii=False),
          " stripShorts:", json.dumps(e["stripShorts"], ensure_ascii=False))
    print(" resistorPower NG:", json.dumps([x for x in e["resistorPower"] if not x["ok"]], ensure_ascii=False),
          " pinConflicts:", json.dumps(e["pinConflicts"], ensure_ascii=False),
          " decouplingValueWarn:", json.dumps(e["decouplingValueWarn"], ensure_ascii=False))
    for w in result["warnings"]:
        print("  *", w)
    if dst:
        io.open(dst, "w", encoding="utf-8").write(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        print(" ->", dst)
