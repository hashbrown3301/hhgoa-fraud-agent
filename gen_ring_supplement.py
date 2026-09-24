import pandas as pd
from agent.detectors import add_profile

target_profile = 'SM-G935F Build/NRD90M | Android 7.0 | chrome 62.0 for android | 1920x1080'

dev = pd.read_csv('data/slice_devices.csv', low_memory=False)
dev['ts'] = pd.to_datetime(dev['ts'])
dev = add_profile(dev)
ring = dev[dev['profile'] == target_profile].copy()

existing_customers = set(pd.read_csv('graph_load/v_customer.csv')['id'])
new_cust = sorted(set(ring['customer_id']) - existing_customers)
ring_new = ring[ring['customer_id'].isin(new_cust)].drop_duplicates('TransactionID')

def esc(s):
    return str(s).replace('"', '\\"')

lines = []
for c in new_cust:
    lines.append(f'  INSERT INTO Customer VALUES ("{esc(c)}");')
    lines.append(f'  INSERT INTO Card VALUES ("{esc(c)}", "", "", "");')
    lines.append(f'  INSERT INTO OWNS VALUES ("{esc(c)}", "{esc(c)}");')

for _, r in ring_new.iterrows():
    tid = str(int(r['TransactionID']))
    ts = r['ts'].strftime('%Y-%m-%d %H:%M:%S')
    channel = esc(r.get('channel', 'online') or 'online')
    amt = float(r['TransactionAmt'])
    product = esc(r.get('ProductCD', '') or '')
    addr1 = '' if pd.isna(r.get('addr1')) else str(r['addr1'])
    score = float(r['risk_score'])
    lines.append(f'  INSERT INTO Txn VALUES ("{tid}", to_datetime("{ts}"), "{channel}", {amt}, "{product}", "{addr1}", "", {score});')
    lines.append(f'  INSERT INTO MADE VALUES ("{esc(r["customer_id"])}", "{tid}");')
    lines.append(f'  INSERT INTO USED_DEVICE VALUES ("{tid}", "{esc(target_profile)}");')

body = "\n".join(lines)
script = f'INTERPRET QUERY () FOR GRAPH FraudGraph {{\n{body}\n}}'
open('ring_supplement.gsql', 'w').write(script)
print(len(lines), 'statements written to ring_supplement.gsql')