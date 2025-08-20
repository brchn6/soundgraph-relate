from __future__ import annotations
import torch, pandas as pd
from pathlib import Path
from torch.utils.data import Dataset

class TextContrastiveDataset(Dataset):
    def __init__(self, corpus_parquet: str | Path, pos_pairs: str | Path, neg_pairs: str | Path):
        self.corpus = pd.read_parquet(corpus_parquet)[["track_id","text"]].drop_duplicates("track_id")
        self.id2text = dict(zip(self.corpus["track_id"], self.corpus["text"]))
        self.pos = pd.read_parquet(pos_pairs)[["a","b"]].values.tolist()
        self.neg = pd.read_parquet(neg_pairs)[["a","b"]].values.tolist()
        self.pairs = [(a,b,1) for a,b in self.pos] + [(a,b,0) for a,b in self.neg]

    def __len__(self): return len(self.pairs)

    def __getitem__(self, idx):
        a,b,y = self.pairs[idx]
        ta = self.id2text.get(a, "")
        tb = self.id2text.get(b, "")
        return {"a_id": a, "b_id": b, "a_text": ta, "b_text": tb, "label": int(y)}
