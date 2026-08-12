import express from 'express';
import { Pool } from 'pg';
import crypto from 'node:crypto';

const app = express();
const db = new Pool({ connectionString: process.env.DATABASE_URL || 'postgres://roof:roof@roof-wallet-db:5432/roof' });
const port = Number(process.env.PORT || 8787);
const testEnabled = String(process.env.TEST_CARD_ENABLED || 'true').toLowerCase() === 'true';
const catalog = {
  premium_1m:{kind:'premium',months:1,price:29900,title:'Roof Premium — 1 month'},
  premium_12m:{kind:'premium',months:12,price:199000,title:'Roof Premium — 12 months'},
  stars_100:{kind:'stars',stars:100,price:9900,title:'100 Roof Stars'},
  stars_500:{kind:'stars',stars:500,price:39900,title:'500 Roof Stars'},
  stars_2500:{kind:'stars',stars:2500,price:149000,title:'2500 Roof Stars'}
};
app.use(express.json());

await db.query(`
CREATE TABLE IF NOT EXISTS accounts(
 user_id text primary key,
 stars bigint not null default 0 check(stars>=0),
 premium_until timestamptz,
 created_at timestamptz not null default now()
);
CREATE TABLE IF NOT EXISTS payments(
 id uuid primary key,
 user_id text not null,
 sku text not null,
 amount_minor bigint not null,
 status text not null,
 created_at timestamptz not null default now()
);
CREATE TABLE IF NOT EXISTS ledger(
 id bigserial primary key,
 user_id text not null,
 kind text not null,
 delta bigint,
 payment_id uuid unique,
 created_at timestamptz not null default now()
);
`);

function uid(v){ const s=String(v||'').trim(); if(!s||s.length>128) throw new Error('bad user'); return s; }
async function wallet(userId){
 await db.query('INSERT INTO accounts(user_id) VALUES($1) ON CONFLICT DO NOTHING',[userId]);
 const r=await db.query('SELECT user_id,stars,premium_until FROM accounts WHERE user_id=$1',[userId]);
 const a=r.rows[0];
 return {userId:a.user_id,stars:Number(a.stars),premiumUntil:a.premium_until,premiumActive:!!a.premium_until&&new Date(a.premium_until)>new Date()};
}

app.get('/health',async(_q,res)=>{try{await db.query('SELECT 1');res.json({ok:true,testEnabled});}catch{res.status(503).json({ok:false});}});
app.get('/v1/wallet/:id',async(req,res)=>{try{res.json(await wallet(uid(req.params.id)));}catch{res.status(400).json({error:'invalid_user_id'});}});
app.get('/v1/catalog',(_q,res)=>res.json({products:Object.entries(catalog).map(([sku,p])=>({sku,...p}))}));

app.post('/v1/payments/test',async(req,res)=>{
 if(!testEnabled) return res.status(403).json({error:'test_disabled'});
 let userId; try{userId=uid(req.body?.userId);}catch{return res.status(400).json({error:'invalid_user_id'});}
 const sku=String(req.body?.sku||''); const card=String(req.body?.card||'').trim(); const p=catalog[sku];
 if(!p) return res.status(400).json({error:'unknown_sku'});
 const id=crypto.randomUUID(); const c=await db.connect();
 try{
  await c.query('BEGIN');
  await c.query('INSERT INTO accounts(user_id) VALUES($1) ON CONFLICT DO NOTHING',[userId]);
  await c.query('INSERT INTO payments(id,user_id,sku,amount_minor,status) VALUES($1,$2,$3,$4,$5)',[id,userId,sku,p.price,card==='1'?'pending':'declined']);
  if(card!=='1'){await c.query('COMMIT'); return res.status(402).json({ok:false,paymentId:id,status:'declined'});}
  await c.query('SELECT * FROM accounts WHERE user_id=$1 FOR UPDATE',[userId]);
  if(p.kind==='stars'){
   await c.query('UPDATE accounts SET stars=stars+$2 WHERE user_id=$1',[userId,p.stars]);
   await c.query('INSERT INTO ledger(user_id,kind,delta,payment_id) VALUES($1,$2,$3,$4)',[userId,'stars',p.stars,id]);
  } else {
   await c.query(`UPDATE accounts SET premium_until=(CASE WHEN premium_until IS NULL OR premium_until<now() THEN now() ELSE premium_until END)+($2::text||' months')::interval WHERE user_id=$1`,[userId,p.months]);
   await c.query('INSERT INTO ledger(user_id,kind,delta,payment_id) VALUES($1,$2,$3,$4)',[userId,'premium_months',p.months,id]);
  }
  await c.query("UPDATE payments SET status='succeeded' WHERE id=$1",[id]);
  await c.query('COMMIT');
  res.json({ok:true,paymentId:id,wallet:await wallet(userId)});
 } catch(e){try{await c.query('ROLLBACK')}catch{}; console.error(e); res.status(500).json({error:'payment_failed'});} finally{c.release();}
});

app.get('/store/',(_q,res)=>res.type('html').send(`<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Roof Store</title><style>body{font:16px system-ui;background:#eef3f8;margin:0;padding:24px}.w{max-width:720px;margin:auto}.c{background:#fff;padding:18px;border-radius:16px;margin:12px 0}input,button{font:inherit;padding:10px;border-radius:10px;border:1px solid #ccd}button{background:#3390ec;color:white;border:0;margin:5px}</style><div class=w><div class=c><h1>Roof Store</h1><p>New accounts: 0 Stars, no Premium. Sandbox test card: <b>1</b>.</p></div><div class=c>User ID <input id=u placeholder='10001'> Card <input id=card value='1'><p id=w></p></div><div class=c id=p></div><div class=c id=r></div></div><script>async function load(){let id=u.value.trim();if(!id)return;let x=await fetch('/v1/wallet/'+encodeURIComponent(id)).then(r=>r.json());w.textContent='Stars: '+x.stars+' · Premium: '+(x.premiumActive?x.premiumUntil:'no')}async function buy(s){let x=await fetch('/v1/payments/test',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({userId:u.value,card:card.value,sku:s})});let j=await x.json();r.textContent=x.ok?'Success: '+j.paymentId:'Declined';load()}fetch('/v1/catalog').then(r=>r.json()).then(j=>{p.innerHTML='<h3>Products</h3>';j.products.forEach(x=>{let b=document.createElement('button');b.textContent=x.title;b.onclick=()=>buy(x.sku);p.appendChild(b)})});u.onchange=load;</script>`));

app.listen(port,'0.0.0.0',()=>console.log('Roof Wallet on',port));
