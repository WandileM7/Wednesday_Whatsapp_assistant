import { useEffect, useRef } from "react"
const SPRITE = [
  [0,0,0,0,1,1,1,1,1,1,1,1,0,0,0,0],[0,0,0,1,1,1,1,1,1,1,1,1,1,0,0,0],
  [0,0,1,1,1,4,1,1,1,1,4,1,1,1,0,0],[0,1,1,1,4,4,1,1,1,1,4,4,1,1,1,0],
  [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0],[1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
  [1,1,2,2,1,1,1,1,1,1,1,1,2,2,1,1],[1,1,2,2,1,1,1,1,1,1,1,1,2,2,1,1],
  [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],[1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
  [0,1,1,1,1,1,3,3,3,3,1,1,1,1,1,0],[0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0],
  [0,0,1,1,1,1,1,1,1,1,1,1,1,1,0,0],[0,0,0,1,1,1,1,1,1,1,1,1,1,0,0,0],
  [0,0,0,0,1,1,1,1,1,1,1,1,0,0,0,0],[0,0,0,0,0,0,1,1,1,1,0,0,0,0,0,0],
]
const SIZE=16,PX=16
function spriteFor(level){
  const open=Math.round(level*3); if(!open)return SPRITE
  const rows=SPRITE.map(r=>r.slice())
  for(let i=0;i<open;i++){const y=11+i;if(y>=SIZE)break;for(let x=6;x<=9;x++)rows[y][x]=3}
  return rows
}
export default function PixelSprite({analyser,speaking}){
  const canvasRef=useRef(null),levelRef=useRef(0),tRef=useRef(0)
  useEffect(()=>{ if(!analyser)return; return analyser.subscribe(l=>{levelRef.current=l}) },[analyser])
  useEffect(()=>{
    const canvas=canvasRef.current,ctx=canvas.getContext("2d"); ctx.imageSmoothingEnabled=false; let raf=0
    const colors={1:"#7c5cff",2:"#0a0a0f",3:"#ff6ad5",4:"#b8a3ff"}
    const draw=()=>{
      const t=(tRef.current+=1),level=levelRef.current,W=canvas.width,H=canvas.height
      ctx.clearRect(0,0,W,H)
      const bob=Math.sin(t*0.04)*6,scale=1+level*0.18,px=PX*scale
      const cx=W/2,cy=H/2+bob,radius=(SIZE*px)/2+18+level*30
      const grad=ctx.createRadialGradient(cx,cy,4,cx,cy,radius)
      grad.addColorStop(0,`rgba(124,92,255,${0.35+level*0.4})`); grad.addColorStop(1,"rgba(124,92,255,0)")
      ctx.fillStyle=grad; ctx.beginPath(); ctx.arc(cx,cy,radius,0,Math.PI*2); ctx.fill()
      const rows=spriteFor(speaking?level:0),ox=cx-(SIZE*px)/2,oy=cy-(SIZE*px)/2
      for(let y=0;y<SIZE;y++)for(let x=0;x<SIZE;x++){const v=rows[y][x];if(!v)continue
        ctx.fillStyle=colors[v]; ctx.fillRect(Math.round(ox+x*px),Math.round(oy+y*px),Math.ceil(px),Math.ceil(px))}
      raf=requestAnimationFrame(draw)
    }
    draw(); return()=>cancelAnimationFrame(raf)
  },[speaking])
  return <canvas ref={canvasRef} width={520} height={520} className="pixelated" style={{width:360,height:360}} />
}