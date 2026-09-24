"""One-time setup: add a vector attribute to ClosedCase, then bulk-load the embeddings."""
from agent.tools import call_tool

print("Adding vector attribute...")
r = call_tool("add_vector_attribute", vertex_type="ClosedCase", vector_name="embedding",
              dimension=384, metric="COSINE")
print(r)