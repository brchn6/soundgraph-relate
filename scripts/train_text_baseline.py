from __future__ import annotations
import torch, pandas as pd
from torch.utils.data import DataLoader
from sentence_transformers import SentenceTransformer, losses, InputExample
from pathlib import Path
from sgr.datasets import TextContrastiveDataset

DL = Path("data/dl")

if __name__ == "__main__":
    model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
    ds = TextContrastiveDataset(DL/"corpus_train.parquet", DL/"pairs_positive.parquet", DL/"pairs_negative.parquet")

    def to_examples(batch):
        examples = []
        for i in range(len(batch["label"])):
            examples.append(InputExample(
                texts=[batch["a_text"][i], batch["b_text"][i]],
                label=float(batch["label"][i])
            ))
        return examples

    def collate(examples):  # Sentence-Transformers expects list[InputExample]
        # we will pass directly a list of InputExample instances
        return examples

    # wrap our dataset with a DataLoader that yields InputExample lists
    class ExampleLoader(torch.utils.data.IterableDataset):
        def __iter__(self):
            loader = DataLoader(ds, batch_size=32, shuffle=True, collate_fn=lambda x: x)  # raw dicts
            for batch in loader:
                # reorganize to column lists
                cols = {k: [d[k] for d in batch] for k in batch[0].keys()}
                yield to_examples(cols)

    train_loader = DataLoader(ExampleLoader(), batch_size=None)
    train_loss = losses.CosineSimilarityLoss(model)

    # small warmup run
    model.fit(train_objectives=[(train_loader, train_loss)], epochs=1, warmup_steps=100, output_path="artifacts/text_baseline")
    print("saved model to artifacts/text_baseline")
