from pathlib import Path
import subprocess,shlex
root=Path(__file__).resolve().parents[1]
# The manifest story omits vendor names; the authorized generator supplies them.
names=['Zelvori Basin Operations LLC','Mavren Fold Interests LLC','Orvessa Field Services LLC','Telnori Fluid Transit LLC','Nacrevale 7-QH','Fennovar 2-RH','Velquorin','Quenvori','Zelvori','Mavren','Orvessa','Telnori','Nacrevale','Fennovar']
lines=[]
for name in names:
 args=['grep','-ril','--',name,'src/','truth/']
 r=subprocess.run(args,cwd=root,capture_output=True,text=True)
 lines+=['$ '+shlex.join(args),r.stdout.rstrip() or '(no output)',f'exit={r.returncode}']
 assert r.returncode==1 and not r.stdout and not r.stderr,(name,r.stdout,r.stderr)
lines+=['PASS: no pilot proper nouns appear in src/ or truth/.']
(root/'audit/gate4.log').write_text('\n'.join(lines)+'\n')
print('\n'.join(lines))
