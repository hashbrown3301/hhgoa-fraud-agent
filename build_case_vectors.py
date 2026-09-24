"""Compute embeddings for every closed case and write a file ready for
load_vectors_from_csv. Run once: python build_case_vectors.py"""
import pandas as pd
from agent.embeddings import embed_texts, closed_case_doc, DIM

cc = pd.read_csv("data/closed_cases_history.csv")
docs = [closed_case_doc(n, p) for n, p in zip(cc["analyst_notes"], cc["pattern"])]

print(f"Embedding {len(docs)} closed cases (dim={DIM})...")
vecs = embed_texts(docs)

with open("graph_load/closed_case_vectors.csv", "w", encoding="utf-8") as f:
    for case_id, v in zip(cc["case_id"], vecs):
        f.write(f"{case_id}|{','.join(str(x) for x in v)}\n")

print(f"Wrote graph_load/closed_case_vectors.csv ({len(vecs)} rows, dim={DIM})")