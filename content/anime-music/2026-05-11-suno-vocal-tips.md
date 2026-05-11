# Suno で日本語ボーカル品質を上げるプロンプト工夫

## 結論

- スタイル指定で `J-pop, female vocal, anime, dramatic, orchestral` のように複合タグで攻める
- 歌詞は `[Verse]` `[Chorus]` `[Bridge]` のセクションタグを必ず付ける
- BPMをスタイル指定欄に明示すると安定する (例: `BPM 142`)

## ALI PROJECT寄りに振りたいとき

- スタイル: `gothic, baroque, neoclassical, japanese female vocal, theatrical`
- 歌詞: 漢字密度を高めに、語尾を「〜なり」「〜たまえ」など古語混じりに
- アウトロは長めに取ると荘厳さが出る
