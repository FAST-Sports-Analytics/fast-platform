"use client";

import Image from "next/image";
import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

type OrgUser = { id:number; full_name:string; email:string; role:string; status:string; products:string[]; eligible_products:string[]; sports:string[]; invitation_status?:string; last_login_at?:string|null };
type Device = { id:number; device_id:string; device_name:string; active:boolean; version?:string; last_seen_at?:string|null; deployment_ring?:string };
type Audit = { id:number; created_at:string; action:string; target:string; details:string };
type Branding = { short_name:string; logo_url:string; primary_colour:string; secondary_colour:string; accent_colour:string };
type Organisation = { id:number; name:string; tier?:string; status:string; max_seats?:number; seats_used:number; active_users:number; active_devices:number; max_devices?:number|null; products:string[]; sports:string[]; branding:Branding; health_checks?:{key:string;ok:boolean;label:string;detail:string}[]; subscription?:{display_status?:string;status?:string;plan?:{name?:string}|null} };
type Overview = { organisation:Organisation; users:OrgUser[]; devices:Device[]; audit:Audit[] };
type UserInfo = { id?:number; full_name?:string; email?:string; role?:string; organisation_admin?:boolean };
type Tab = "overview"|"users"|"access"|"devices"|"branding"|"audit";

const roles = ["administrator","analyst","coach","scout"];
function apiBase(){ return (process.env.NEXT_PUBLIC_FAST_CLOUD_URL || "http://127.0.0.1:8766").replace(/\/+$/,""); }
function nice(value:string){ return value.replaceAll("_"," ").replace(/\b\w/g, c=>c.toUpperCase()); }
function dateTime(value?:string|null){ if(!value) return "Never"; const d=new Date(value); return Number.isNaN(d.valueOf())?value:new Intl.DateTimeFormat("en-GB",{dateStyle:"medium",timeStyle:"short"}).format(d); }

export default function OrganisationPage(){
  const router=useRouter();
  const [me,setMe]=useState<UserInfo>({});
  const [data,setData]=useState<Overview|null>(null);
  const [tab,setTab]=useState<Tab>("overview");
  const [loading,setLoading]=useState(true);
  const [working,setWorking]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [editing,setEditing]=useState<OrgUser|null>(null);
  const [adding,setAdding]=useState(false);
  const [branding,setBranding]=useState<Branding>({short_name:"",logo_url:"",primary_colour:"#19D978",secondary_colour:"#151A1D",accent_colour:"#19D978"});

  function token(){ return typeof window==="undefined"?"":sessionStorage.getItem("fast_access_token")||""; }
  async function api(path:string, init:RequestInit={}){
    const auth=token(); if(!auth) throw new Error("Your FAST Cloud session has ended. Please log in again.");
    const res=await fetch(`${apiBase()}${path}`,{...init,headers:{Accept:"application/json",...(init.body?{"Content-Type":"application/json"}:{}),Authorization:`Bearer ${auth}`,...(init.headers||{})}});
    const body=await res.json().catch(()=>({}));
    if(res.status===401){ sessionStorage.removeItem("fast_access_token"); router.replace("/login"); throw new Error("Your FAST Cloud session has ended."); }
    if(res.status===403){ router.replace("/account"); throw new Error("Organisation administrator access required."); }
    if(!res.ok) throw new Error(typeof body.detail==="string"?body.detail:body.detail?.message||"FAST Cloud request failed.");
    return body;
  }
  async function load(){ setLoading(true); setError(""); try{ const [profile,overview]=await Promise.all([api("/api/v1/auth/me"),api("/api/v1/organisation-management")]); setMe(profile); setData(overview); setBranding(overview.organisation.branding); sessionStorage.setItem("fast_user",JSON.stringify(profile)); }catch(e){setError(e instanceof Error?e.message:"Organisation Management could not load.");}finally{setLoading(false);} }
  useEffect(()=>{ if(!sessionStorage.getItem("fast_access_token")){router.replace("/login");return;} load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ },[router]);
  async function mutate(path:string, init:RequestInit, success:string){ setWorking(true);setError("");setMessage("");try{const next=await api(path,init);setData(next);if(next.organisation?.branding)setBranding(next.organisation.branding);setMessage(success);return true;}catch(e){setError(e instanceof Error?e.message:"The change could not be saved.");return false;}finally{setWorking(false);} }
  function logout(){sessionStorage.removeItem("fast_access_token");sessionStorage.removeItem("fast_refresh_token");sessionStorage.removeItem("fast_user");router.replace("/login");}
  const org=data?.organisation;
  const assigned=useMemo(()=>data?.users.reduce((n,u)=>n+u.products.length,0)||0,[data]);

  if(loading) return <main className="account-page"><div className="account-shell"><p className="eyebrow">FAST Cloud</p><h1>Loading Organisation Management…</h1></div></main>;
  if(!data||!org) return <main className="account-page"><div className="account-shell"><div className="account-message error">{error||"Organisation Management is unavailable."}</div><Link className="button button-quiet" href="/account">Back to account</Link></div></main>;

  return <main className="account-page">
    <header className="account-header"><Link className="account-brand" href="/"><Image src="/branding/fast-logo.png" alt="FAST Sports Analytics" width={500} height={170}/></Link><div className="account-header-actions"><Link href="/account" className="text-link">Account</Link><Link href="/downloads" className="text-link">Downloads</Link><button className="button button-quiet button-small" onClick={logout}>Log out</button></div></header>
    <div className="account-shell org-shell">
      <div className="account-title-row"><div><p className="eyebrow">FAST Cloud</p><h1>Organisation Management</h1><p>{org.name} · {me.full_name||me.email} · Administrator</p></div><span className="account-status">{org.subscription?.display_status||org.status}</span></div>
      {error&&<div className="account-message error">{error}</div>}{message&&<div className="account-message success">{message}</div>}
      <nav className="org-tabs" aria-label="Organisation Management sections">{(["overview","users","access","devices","branding","audit"] as Tab[]).map(value=><button key={value} className={tab===value?"active":""} onClick={()=>{setTab(value);setMessage("");setError("");}}>{nice(value)}</button>)}</nav>

      {tab==="overview"&&<>
        <section className="account-panel"><div className="account-panel-heading"><div><p className="eyebrow">Organisation</p><h2>{org.name}</h2></div><Link className="button button-quiet button-small" href="/account">Subscription & billing</Link></div>
          <div className="account-metrics"><article><small>User seats</small><strong>{org.seats_used} / {org.max_seats??"—"}</strong></article><article><small>Active users</small><strong>{org.active_users}</strong></article><article><small>Active devices</small><strong>{org.active_devices} / {org.max_devices??"—"}</strong></article><article><small>Assigned products</small><strong>{assigned}</strong></article></div>
          <div className="account-entitlements">{org.products.map(p=><span key={p}>FAST {nice(p)}</span>)}{org.sports.map(s=><span key={s}>{nice(s)}</span>)}</div>
        </section>
        <section className="account-panel"><p className="eyebrow">Cloud health</p><h2>Organisation status</h2><div className="org-health">{(org.health_checks||[]).map(item=><article key={item.key} className={item.ok?"ok":"warn"}><strong>{item.label}</strong><span>{item.detail}</span></article>)}</div></section>
      </>}

      {tab==="users"&&<section className="account-panel"><div className="account-panel-heading"><div><p className="eyebrow">Users & seats</p><h2>Organisation users</h2><p>{org.seats_used} of {org.max_seats??"—"} licensed user seats allocated.</p></div><button className="button button-primary button-small" onClick={()=>setAdding(true)}>Invite user</button></div><div className="org-table-wrap"><table className="org-table"><thead><tr><th>User</th><th>Role</th><th>Status</th><th>Products</th><th>Last login</th><th></th></tr></thead><tbody>{data.users.map(u=><tr key={u.id}><td><strong>{u.full_name||"Unnamed user"}</strong><small>{u.email}</small>{u.scheduled_access_release&&<small className="org-scheduled-note">Licensed access ends {dateTime(u.scheduled_access_release_at)}</small>}</td><td>{nice(u.role)}</td><td><span className={`org-pill ${u.status}`}>{nice(u.status)}</span>{u.scheduled_access_release&&<><br/><span className="org-pill invited">Scheduled for removal</span></>}</td><td>{u.products.length?u.products.map(nice).join(", "):"None"}</td><td>{dateTime(u.last_login_at)}</td><td><button className="button button-quiet button-small" onClick={()=>setEditing(u)}>Manage</button></td></tr>)}</tbody></table></div></section>}

      {tab==="access"&&<section className="account-panel"><p className="eyebrow">Product access</p><h2>Assignments</h2><p>Product assignments remain constrained by each user's role and your organisation licence.</p><div className="org-access-grid">{data.users.map(u=><article key={u.id}><div><strong>{u.full_name||u.email}</strong><small>{nice(u.role)}</small></div><div className="org-checks">{u.eligible_products.length?u.eligible_products.map(product=><label key={product}><input type="checkbox" checked={u.products.includes(product)} disabled={working} onChange={async e=>{const products=e.target.checked?[...u.products,product]:u.products.filter(p=>p!==product);await mutate(`/api/v1/organisation-management/users/${u.id}`,{method:"PATCH",body:JSON.stringify({full_name:u.full_name,role:u.role,status:u.status,products,sports:u.sports})},`${u.full_name||u.email} product access updated.`);}}/>{nice(product)}</label>):<span>No licensed products are available for this role.</span>}</div></article>)}</div></section>}

      {tab==="devices"&&<section className="account-panel"><div className="account-panel-heading"><div><p className="eyebrow">Devices</p><h2>Activated devices</h2><p>{org.active_devices} of {org.max_devices??"—"} active device allocations.</p></div></div><div className="org-table-wrap"><table className="org-table"><thead><tr><th>Device</th><th>Version</th><th>Ring</th><th>Last seen</th><th>Status</th><th></th></tr></thead><tbody>{data.devices.map(d=><tr key={d.id}><td><strong>{d.device_name||d.device_id}</strong><small>{d.device_id}</small>{d.scheduled_deactivation&&<small className="org-scheduled-note">Deactivates {dateTime(d.scheduled_deactivation_at)}</small>}</td><td>{d.version||"—"}</td><td>{nice(d.deployment_ring||"production")}</td><td>{dateTime(d.last_seen_at)}</td><td><span className={`org-pill ${d.active?"active":"suspended"}`}>{d.active?"Active":"Inactive"}</span>{d.scheduled_deactivation&&<><br/><span className="org-pill invited">Scheduled for deactivation</span></>}</td><td><button className={`button button-small ${d.active?"button-danger":"button-primary"}`} disabled={working} onClick={()=>mutate(`/api/v1/organisation-management/devices/${d.id}/${d.active?"deactivate":"reactivate"}`,{method:"POST"},`${d.device_name||"Device"} ${d.active?"deactivated":"reactivated"}.`)}>{d.active?"Deactivate":"Reactivate"}</button></td></tr>)}</tbody></table></div></section>}

      {tab==="branding"&&<section className="account-panel"><p className="eyebrow">Branding</p><h2>Organisation identity</h2><p>These values are used by FAST clients when organisation branding is displayed.</p><form className="org-form" onSubmit={async e=>{e.preventDefault();await mutate("/api/v1/organisation-management/branding",{method:"PATCH",body:JSON.stringify(branding)},"Organisation branding updated.");}}><label>Short name<input value={branding.short_name} maxLength={40} onChange={e=>setBranding({...branding,short_name:e.target.value})}/></label><label className="wide">Logo URL<input type="url" value={branding.logo_url} onChange={e=>setBranding({...branding,logo_url:e.target.value})} placeholder="https://…"/></label><label>Primary colour<div className="org-colour"><input type="color" value={branding.primary_colour} onChange={e=>setBranding({...branding,primary_colour:e.target.value.toUpperCase()})}/><input value={branding.primary_colour} onChange={e=>setBranding({...branding,primary_colour:e.target.value})}/></div></label><label>Secondary colour<div className="org-colour"><input type="color" value={branding.secondary_colour} onChange={e=>setBranding({...branding,secondary_colour:e.target.value.toUpperCase()})}/><input value={branding.secondary_colour} onChange={e=>setBranding({...branding,secondary_colour:e.target.value})}/></div></label><label>Accent colour<div className="org-colour"><input type="color" value={branding.accent_colour} onChange={e=>setBranding({...branding,accent_colour:e.target.value.toUpperCase()})}/><input value={branding.accent_colour} onChange={e=>setBranding({...branding,accent_colour:e.target.value})}/></div></label><div className="wide"><button className="button button-primary" disabled={working}>{working?"Saving…":"Save branding"}</button></div></form></section>}

      {tab==="audit"&&<section className="account-panel"><p className="eyebrow">Audit log</p><h2>Organisation activity</h2><p>The latest meaningful organisation-management activity recorded by FAST Cloud.</p><div className="org-table-wrap"><table className="org-table"><thead><tr><th>Date</th><th>Action</th><th>Target</th><th>Details</th></tr></thead><tbody>{data.audit.map(a=><tr key={a.id}><td>{dateTime(a.created_at)}</td><td>{nice(a.action)}</td><td>{a.target||"—"}</td><td>{a.details||"—"}</td></tr>)}</tbody></table></div></section>}
    </div>

    {(adding||editing)&&<UserModal user={editing} organisation={org} working={working} onClose={()=>{setAdding(false);setEditing(null);}} onSave={async payload=>{const ok=await mutate(editing?`/api/v1/organisation-management/users/${editing.id}`:"/api/v1/organisation-management/users",{method:editing?"PATCH":"POST",body:JSON.stringify(payload)},editing?"User access updated.":"Invitation sent.");if(ok){setAdding(false);setEditing(null);}}} onRemove={editing?async()=>{if(!confirm(`Remove ${editing.full_name||editing.email} from this organisation? Their seat allocation will be reclaimed.`))return;const ok=await mutate(`/api/v1/organisation-management/users/${editing.id}`,{method:"DELETE"},"User removed and seat reclaimed.");if(ok)setEditing(null);}:undefined} onResend={editing?.status==="invited"?async()=>{await mutate(`/api/v1/organisation-management/users/${editing.id}/resend-invite`,{method:"POST"},"Invitation resent.");}:undefined}/>} 
  </main>;
}

function UserModal({user,organisation,working,onClose,onSave,onRemove,onResend}:{user:OrgUser|null;organisation:Organisation;working:boolean;onClose:()=>void;onSave:(payload:Record<string,unknown>)=>Promise<void>;onRemove?:()=>Promise<void>;onResend?:()=>Promise<void>}){
  const [name,setName]=useState(user?.full_name||""); const [email,setEmail]=useState(user?.email||""); const [role,setRole]=useState(user?.role||"analyst"); const [status,setStatus]=useState(user?.status||"active"); const [products,setProducts]=useState<string[]>(user?.products||[]); const [sports,setSports]=useState<string[]>(user?.sports||organisation.sports||[]);
  const eligible=role==="administrator"?organisation.products:role==="analyst"?organisation.products.filter(p=>["analysis","viewer"].includes(p)):role==="coach"?organisation.products.filter(p=>p==="viewer"):role==="scout"?organisation.products.filter(p=>p==="scout"):[];
  useEffect(()=>setProducts(current=>current.filter(p=>eligible.includes(p))),[role]); // eslint-disable-line react-hooks/exhaustive-deps
  async function submit(e:FormEvent){e.preventDefault();await onSave(user?{full_name:name,role,status,products,sports}:{full_name:name,email,temporary_password:"",role,products,sports});}
  return <div className="account-modal-backdrop"><section className="account-modal org-user-modal"><button className="account-modal-close" onClick={onClose}>×</button><p className="eyebrow">{user?"Manage user":"New organisation user"}</p><h2>{user?name||email:"Invite user"}</h2><form className="org-form" onSubmit={submit}><label>Full name<input required value={name} onChange={e=>setName(e.target.value)}/></label><label>Email address<input required type="email" disabled={Boolean(user)} value={email} onChange={e=>setEmail(e.target.value)}/></label><label>Role<select value={role} onChange={e=>setRole(e.target.value)}>{roles.map(r=><option key={r} value={r}>{nice(r)}</option>)}</select></label>{user&&<label>Status<select value={status} onChange={e=>setStatus(e.target.value)}><option value="active">Active</option><option value="suspended">Suspended</option>{user.status==="invited"&&<option value="invited">Invited</option>}</select></label>}<fieldset className="wide"><legend>Products</legend><div className="org-checks">{eligible.map(p=><label key={p}><input type="checkbox" checked={products.includes(p)} onChange={e=>setProducts(e.target.checked?[...products,p]:products.filter(v=>v!==p))}/>{nice(p)}</label>)}</div></fieldset><fieldset className="wide"><legend>Sports</legend><div className="org-checks">{organisation.sports.map(s=><label key={s}><input type="checkbox" checked={sports.includes(s)} onChange={e=>setSports(e.target.checked?[...sports,s]:sports.filter(v=>v!==s))}/>{nice(s)}</label>)}</div></fieldset><div className="wide account-modal-actions">{onRemove&&<button type="button" className="button button-danger" disabled={working} onClick={onRemove}>Remove from organisation</button>}{onResend&&<button type="button" className="button button-quiet" disabled={working} onClick={onResend}>Resend invitation</button>}<button className="button button-primary" disabled={working}>{working?"Saving…":user?"Save changes":"Send invitation"}</button></div></form></section></div>;
}
