#!/usr/bin/env python3
"""Convert manually verified subtitle cues from a timeline into an SRT."""
import argparse,json
from pathlib import Path
from validate_timeline import read_json, validate

def ts(t):
 ms=round(t*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
 return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'
def main():
 p=argparse.ArgumentParser();p.add_argument('timeline',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
 timeline=a.timeline.resolve();errors=validate(timeline)
 if errors:p.error('; '.join(errors))
 cues=read_json(timeline).get('subtitles',[])
 cues=sorted(cues,key=lambda x:x['start'])
 for i,c in enumerate(cues[1:],1):
  if c['start']<cues[i-1]['end']-0.001:p.error('Overlapping subtitle cues')
 lines=[]
 for i,c in enumerate(cues,1):lines.extend([str(i),f"{ts(c['start'])} --> {ts(c['end'])}",c['text'].strip(),''])
 out=a.output or timeline.parent/'subtitles.srt';out.parent.mkdir(parents=True,exist_ok=True);out.write_text('\n'.join(lines),encoding='utf-8-sig')
 print(out)
if __name__=='__main__':main()
