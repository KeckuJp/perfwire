---
name: perfwire
description: Plans and audits hand-soldered perfboard (universal board / protoboard) wiring together with a human. Generates perfwire board-state JSON from a netlist/schematic, runs solver.py to place/route/audit under physical and EE constraints, and audits the human's edits from the index.html drag editor against physical reality. Use for perfboard / protoboard / universal board / jumper wiring / solder bridge / wiring plan / netlist-to-board requests. ユニバーサル基板・穴あき基板・配線計画・はんだブリッジ・perfwire の依頼で使用。
---

# perfwire — AI×人間のユニバーサル基板配線計画

## 原則

1. **写真から穴位置を推測しない**。実機の位置は人間がエディタ（index.html）のドラッグで入力する。AIの担当は「計画・割付・監査」。
2. **銅線は部品と同じ穴に挿せない**。被覆線の端は「ターゲットの足に隣接する空き穴＋はんだブリッジ」。空きが無いときだけ足へ直付け（`direct: true`）。
3. 正しさの根拠は常に**状態JSON**（README のスキーマ参照）。エディタと solver.py は同じスキーマを読み書きする。

## ワークフロー

### 1. 新規プロジェクト（回路図/ネットリスト → 状態JSON）

ユーザーの回路から以下を組み立てて `<project>.json` を書く:

- `grid`: 実基板の穴数（ユーザーに確認）。ストリップ基板（ベロボード）は `grid.type:"strip"` ＋ `stripAxis:"row"|"col"`、`trackCuts:[[[c,r],[c2,r2]],…]` で銅箔ストリップとカットを表現（同一未カットストリップに異ネット＝`stripShorts` ＝ショート）
- `parts`: 各部品。kind は `ic`（pins辞書: DIP-8 はピン行間が3穴）/ `r` / `film` / `disc` / `elec`（plus=0 で leads[0] が＋極）。`leadNames` は `<id>.a/.b`（IC は `<id>.<pin>`）。動かせない部品は `locked: true`
- `leads`: 全リードの `{net, at}`。外部線は `W.` プレフィックスの単独リード。任意 `role` で電気的役割を宣言できる（`out`/`in`/`bidir`/`pwr`/`pwr_in`/`passive`/`oc`/`tri`/`nc`/`test`）。**外部の MCU 出力や電源が線で入ってくる端子は role を付ける**（例: `W.MCU_TX`→`role:"out"`、`W.RED`→`role:"pwr"`）。これにより基板外ドライバも出力競合検査の対象になる
- `parts`（IC）: 任意 `pinTypes`（ピン番号→役割。例 opamp-ic: `{"1":"out","2":"in","3":"in","4":"pwr_in","5":"in","6":"in","7":"out","8":"pwr_in"}`）。**IC 生成時に datasheet から埋める**と出力競合・電源ピン検査が有効化される
- `netColors`: ネットごとの表示色
- `blockedHoles`: 物理的に使えない穴（ユーザーに確認）

### 2. ソルバー実行

```bash
# macOS/Linux は python3、Windows は python。エージェントは自分が動いている解釈系で呼ぶ（CI と同じ）。
python3 solver.py <project>.json --lint                                               # 契約検証（生成直後に推奨）。クラッシュではなく構造化診断
python3 solver.py <project>.json --propose --config config.example.json -o out.json   # 配置提案+配線+監査
python3 solver.py <project>.json --config config.example.json -o out.json             # 配線のみ（配置は維持）
python3 solver.py <project>.json --emit-config -o perfwire_config.json                # 状態から config 叩き台を生成（要レビュー）
python3 solver.py <project>.json --propose-n --config config.example.json             # 重み格子で最良配置を探索
python3 solver.py out.json --emit-packet -o build_packet.md                           # BOM＋切断長＋ブリッジのビルドパケット
python3 solver.py out.json --guard INA_P --config config.example.json -o guarded.json # 高Zネットのガードリングを合成（案）
python3 solver.py out.json --guard INA_P --guard-net SPK_OUT --config config.example.json -o guarded.json # ガード電位を明示指定
```

**生成した JSON は `--lint` で先に検証する**: 欠落キー・型不正・未知 kind・refdes 重複などの契約違反を、traceback ではなく人間可読な診断（error/warn）で返す。error があれば他のコマンドも実行前にクリーンに停止する。`--guard` 自動推定で候補が複数あると stderr に `ambiguous` 警告＋スコア付き候補一覧が出る（黙って先頭採用しない）＝ `--guard-net` で明示するか `config.guard_of` を設定する。`rail_volts`（V3V3/VMID/GND）は既定 config に同梱済みで、抵抗に `value`Ω があれば消費電力監査がそのまま効く。

**`--config` は必須**: 省くと solver は内蔵 DEF_CFG にフォールバックし、デカップリング距離と配線長の監査が空になる（スキルの中核機能が無言で無効化される）。同梱の `perfwire_config.json` は `config.example.json` と同内容で、`--config` 無指定時の既定パス＝どちらを渡しても結果は同じ。しきい値（部品寸法・ネットクラス・デカップリング近接・重み）はこの JSON をコピーして調整。
solver.py は標準ライブラリのみ（インストール不要）。出力の `stats` / `ee` / `warnings` を必ず確認し、NG はユーザーに報告する。

### 3. 人間の修正

`index.html` をブラウザで開いてもらう。OS別: macOS `open <target>` / Linux `xdg-open <target>` / Windows PowerShell `Start-Process <target>`（cmd は `start "" <target>`）。

**盤面プリロード（推奨）**: `<target>` に裸の `index.html` ではなく、`python3 tools/make_link.py out.json` が出力する `index.html#z=...` ディープリンクを渡すと、開いた瞬間に out.json の盤面が新規案として読み込まれる（既存の編集は保持＝非破壊）。`file://` で開くなら絶対パス＋ハッシュ（例 `file:///path/to/index.html#z=...`、Windows はバックスラッシュを `/` に）。`make_link.py` は**フラット形状**（solver の out.json／エディタの「書き出し」）専用。`examples/client-hardware_tap_buffer.json` は `proposals[]` 形状なので渡せない。
プリロードしない場合は out.json を「開く…」かドラッグ&ドロップで読み込み。
ドラッグ修正 → 「書き出し」。エディタ内にも同じソルバーが内蔵されており、人間がスライダー＋再計算で自走できる。

実機の記録（リバース）の場合は、**写真下絵**を案内する: 実機写真をエディタにドロップ →
不透明度/拡大/回転/左右反転（裏面写真）で穴を合わせる → 部品をなぞってドラッグ。
AI が写真から穴位置を読むのではなく、人間が写真をトレースするのが正しい分担。

### 4. 監査と確定

ユーザーから戻ってきた JSON を solver.py（配線のみモード）または独自チェックで監査:

- **ERC（はんだ前チェック）** — `ee` ブロックを必ず確認しユーザーに報告: `openNets`（未連結ネット）/ `unconnectedLeads`（ネット未割当の足）/ `duplicateIds`（refdes 重複）/ `multipleDrivers`（**出力-出力ショート＝ドライバ競合**。同一ネットに role=out が2本以上。基板外 MCU 出力端子も含む）/ `floatingPowerPins`（電源ピン浮き）/ `singleLeadNets`（単一リード=結線漏れ。`rules.single_lead_allowlist` で I/O 点は除外）/ `unclassifiedNets`（クラス未割当＝EEルール素通り）/ `polarity`（電解の逆極性。`rail_rank` 設定時に有効）/ `powerReach`（PWRネットが給電リードに到達。`power_entry` 設定時）/ `keepAway`（高Zノードの離隔違反）/ `decouplingCoverage`（電源ピンのバイパス存在）。`undrivenNets`（入力のみで駆動なし＝フローティング。passive バイアスは除外）/ `stripShorts`（ストリップ基板で異ネットが同一未カットストリップに同居）/ `resistorPower`（任意 `value`Ω＋`rail_volts` 設定時、P=ΔV²/R が定格超）/ `decouplingValueWarn`（バイパスに 1µF 超）/ `pinConflicts`（同一ネットに out と pwr＝出力を電源に短絡）。`ee.fabReady`（=eeNg 0）が総合ゲート。`ee.fixes` に各指摘の機械可読な対処案が付く（advisory）。**出力競合・電源ピン・値考慮検査は `pinTypes`/`role`/`value`/`rail_volts` が宣言された場合のみ作動**（未宣言は誤検出回避でスキップ＝後方互換）
- 各ネットが連結か（union-find）/ 別ネットのパッドがブリッジされていないか
- デカップリング距離・クラス別配線長・本体重なり（tall×tall=NG）・パッド接合数
- **トポロジ/SI レビュー** — `ee.grounding`（スター/デイジーチェーン判定。リターンネットが daisy-chain なら共通インピーダンス結合の警告）/ `ee.guard`（高Zノードのガード助言）/ `ee.crosstalk`（平行近接の被覆線対。端点近似＝経路未モデルのため助言）
- PASS したら、はんだ作業はエディタの**作業ガイド**（1手順ずつハイライト・裏面ミラービュー・進捗保存）を案内する
- 実機検証はエディタの**導通リスト**ボタン（ネット別ビープアウト + ブリッジ厳禁ペアの markdown）と
  **テスターモード**（2穴クリックで計画上の導通判定）を案内する。独自チェックリストを別途生成してもよい

## 注意

- 同値の抵抗は役割を入れ替えても電気的に等価。役割の同定は「ICのどのピンにブリッジ済みか」を最優先の証拠にする
- 案（proposals）は比較のために残し、採用案を明示する
- 状態JSONは git にコミットして履歴を残す運用を推奨
