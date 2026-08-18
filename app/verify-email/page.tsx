"use client";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

function apiBase(){return (process.env.NEXT_PUBLIC_FAST_CLOUD_URL || "http://127.0.0.1:8766").replace(/\/+$/, "");}
export default function VerifyEmail(){
  const params=useSearchParams(); const token=params.get("token")||"";
  const [state,setState]=useState<"working"|"ok"|"error">("working");
  const [message,setMessage]=useState("Verifying your email address…");
  useEffect(()=>{ if(!token){setState("error");setMessage("This verification link is invalid.");return;}
    fetch(`${apiBase()}/api/v1/auth/verify-email`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token})})
      .then(async r=>{const d=await r.json().catch(()=>({})); if(!r.ok) throw new Error(d.detail||"Verification failed."); setState("ok");setMessage("Your email is verified. You can now sign in and choose your FAST plan.");})
      .catch(e=>{setState("error");setMessage(e instanceof Error?e.message:"Verification failed.");});
  },[token]);
  return <main className="auth-page"><Link href="/" className="auth-brand"><Image src="/branding/fast-logo.png" alt="FAST Sports Analytics" width={420} height={142}/></Link>
    <section className="auth-card"><p className="eyebrow">Account verification</p><h1>{state==="ok"?"You're verified.":state==="error"?"Verification problem":"One moment…"}</h1><p>{message}</p>{state==="ok"&&<Link className="button button-primary" href="/login">Sign in to FAST</Link>}{state==="error"&&<Link href="/contact">Contact FAST support →</Link>}</section>
  </main>;
}
