"""Load the closed-case embeddings into TigerGraph."""
from agent.tools import call_tool

print("Loading vectors...")
r = call_tool("load_vectors_from_csv", vertex_type="ClosedCase", vector_attribute="embedding",
              file_path="graph_load/closed_case_vectors.csv")
print(r)