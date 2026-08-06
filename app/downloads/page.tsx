import Link from "next/link";
import { PageShell } from "../components/PageShell";

const downloads=[
{name:"FAST Launcher",status:"Private beta",text:"Sign in, verify your licence, check for updates and open the FAST products available to your account."},
{name:"FAST Analysis",status:"Private beta",text:"Desktop match coding and performance analysis for modern Windows environments."},
{name:"FAST Viewer",status:"Private beta",text:"Focused clip review, playlists, comments and telestration for coaches."},
{name:"FAST Scout",status:"In development",text:"Structured observations, player reports and connected recruitment workflows."}
];
export default function Downloads(){return <PageShell><section className="page-hero"><p className="eyebrow">Downloads</p><h1>Your FAST workspace.<br/><span>Ready when your account is.</span></h1><p className="lead">Public downloads are not yet available. Early-access users will receive approved releases through FAST Launcher and their licensed account.</p></section><section className="content-section"><div className="download-list">{downloads.map((item,index)=><article key={item.name}><span>{String(index+1).padStart(2,"0")}</span><div><small>{item.status}</small><h2>{item.name}</h2><p>{item.text}</p></div><button disabled>Not yet available</button></article>)}</div><div className="info-panel"><div><p className="eyebrow">Release model</p><h2>Controlled, account-based delivery</h2></div><p>FAST Launcher will manage authenticated access, permitted products and approved updates. Confirmed system requirements, release notes and installation guidance will appear here before public release.</p><Link className="inline-link" href="/docs">Read documentation <span>→</span></Link></div></section></PageShell>}
