from __future__ import annotations
import torch
from torch_geometric.nn import SAGEConv
from torch_geometric.utils import train_test_split_edges

G = torch.load("data/gnn/track_graph.pt")
edge_index, x = G["edge_index"], G["x"]

class SAGE(torch.nn.Module):
    def __init__(self, in_dim, hid=64, out=128):
        super().__init__()
        self.conv1 = SAGEConv(in_dim, hid)
        self.conv2 = SAGEConv(hid, out)

    def forward(self, x, edge_index):
        h = self.conv1(x, edge_index).relu()
        h = self.conv2(h, edge_index)
        return h

if __name__ == "__main__":
    # edge split for link prediction
    data = type("obj",(object,),{})()
    data.x = x
    data.edge_index = edge_index
    split = train_test_split_edges(data)
    model = SAGE(in_dim=x.size(1))
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device); x = x.to(device)
    pos_train_edge = split.train_pos_edge_index.to(device)
    pos_val = split.val_pos_edge_index.to(device)
    neg_val = split.val_neg_edge_index.to(device)

    def score(z, ei):
        # dot-product score
        return (z[ei[0]] * z[ei[1]]).sum(dim=-1)

    bce = torch.nn.BCEWithLogitsLoss()

    for epoch in range(5):
        model.train(); opt.zero_grad()
        z = model(x, pos_train_edge)           # use train edges for message passing
        s_pos = score(z, pos_train_edge)
        # sample negs same size as pos
        neg_idx = torch.randint(0, z.size(0), pos_train_edge.shape, device=device)
        s_neg = score(z, neg_idx)
        y = torch.cat([torch.ones_like(s_pos), torch.zeros_like(s_neg)])
        s = torch.cat([s_pos, s_neg])
        loss = bce(s, y)
        loss.backward(); opt.step()

        # quick val AUC
        model.eval()
        with torch.no_grad():
            z = model(x, pos_train_edge)
            from sklearn.metrics import roc_auc_score
            svp = score(z, pos_val).cpu().numpy()
            svn = score(z, neg_val).cpu().numpy()
            yv = [1]*len(svp) + [0]*len(svn)
            auc = roc_auc_score(yv, list(svp)+list(svn))
        print(f"epoch {epoch} loss={loss.item():.4f} valAUC={auc:.3f}")

    torch.save({"state_dict": model.state_dict()}, "artifacts/gnn_sage.pt")
    print("saved artifacts/gnn_sage.pt")
