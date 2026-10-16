# ADR 0002: python-pptx + narrow Open XML edits

2026-10-16 / Accepted

既存テンプレートをpython-pptxで読み込み、元のslideMaster/slideLayout/themeを保持して新規slideを追加する。図形/コネクタ/表/データ埋込chartはネイティブ。モデルは座標・XMLを渡さず、Pydantic semantic SlideSpecを渡す。

再アップロード済みPPTXの部分修正はpackageをpython-pptxで再保存せず、必要なXMLだけ変更する。対象外OPCエントリーをbyte identicalに維持し、変更前ファイルを保存する。対応を単純text shapeに限定し、未知の形状/装飾runは停止する。

SlideSpec1.0の図配置はDAG rankと定型layout。loop/密図は分割を求める。比較/タイムラインは順序ノード。文字fitは保守的推定。最大2回、領域拡張のみを試し承認済み本文・数値・フォントサイズを変更しない。
