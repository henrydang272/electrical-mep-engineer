import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
rows=[r.rstrip('\n').split('\t') for r in open('g_E-2000b.tsv',encoding='utf8',errors='replace')]
pts=lambda s:[tuple(map(float,q.split(','))) for q in s.split()]
route=[(-192179,103683),(-193254,103683),(-193254,39641),(-200297,39641),(-303322,39641)]
fig,ax=plt.subplots(figsize=(16,10),dpi=110); g=[];t=[]
for p in rows:
    if len(p)>=3 and p[1]=='L':
        v=pts(p[2]); (t if p[0].startswith('E-CABL-TRAY') else g).extend(v[i:i+2] for i in range(len(v)-1))
    if len(p)>3 and 'DP06B-001' in p[3]:
        (x0,y0),_=pts(p[2]); ax.text(x0,y0,p[3],fontsize=8,color='blue',clip_on=True)
ax.add_collection(LineCollection(g,colors='0.8',lw=.3)); ax.add_collection(LineCollection(t,colors='salmon',lw=.4))
ax.plot(*zip(*route),color='magenta',lw=2.5,label='1x5C-2.5mm2 (DP06B-001) L1,L2,L3 = 175.2 m')
ax.legend(loc='upper left'); ax.set_xlim(-315000,-180000); ax.set_ylim(25000,112000); ax.set_aspect('equal'); ax.axis('off')
fig.savefig('route_L1.png',bbox_inches='tight')
