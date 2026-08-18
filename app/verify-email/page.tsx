"use client";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";

export default function VerifyEmail(){
  const [state,setState]=useState<"working"|"ok"|"error">("working");
  const [message,setMessage]=useState("Verifying your email address…");
  useEffect(()=>{ const token=new URLSearchParams(window.location.search).get("token")||"";
    if(!token){setState("error");setMessage("This verification link is invalid.");return;}
    fetch("/api/onboarding/verify-email",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token})})
      .then(async r=>{const d=await r.json().catch(()=>({})); if(!r.ok) throw new Error(d.detail||"Verification failed."); setState("ok");setMessage("Your email is verified. You can now sign in and choose your FAST plan.");})
      .catch(e=>{setState("error");setMessage(e instanceof Error?e.message:"Verification failed.");});
  },[]);
  return <main className="auth-page"><Link href="/" className="auth-brand"><Image src="/branding/fast-logo.png" alt="FAST Sports Analytics" width={420} height={142}/></Link>
    <section className="auth-card"><p className="eyebrow">Account verification</p><h1>{state==="ok"?"You're verified.":state==="error"?"Verification problem":"One moment…"}</h1><p>{message}</p>{state==="ok"&&<Link className="button button-primary" href="/login" style={{ color: "#04150d" }}>Sign in to FAST</Link>}{state==="error"&&<Link href="/contact">Contact FAST support →</Link>}</section>
  </main>;
}
