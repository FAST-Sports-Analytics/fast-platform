import type { MetadataRoute } from "next";
import { products, sports } from "./components/site-data";
export default function sitemap(): MetadataRoute.Sitemap {
  const base="https://www.fastsportsanalytics.com";
  const staticRoutes=["","/platform","/sports","/pricing","/downloads","/docs","/contact","/trial","/login","/privacy","/terms"];
  return [...staticRoutes.map(route=>({url:`${base}${route}`,changeFrequency:"monthly" as const,priority:route===""?1:.7})),...products.map(product=>({url:`${base}/platform/${product.slug}`,changeFrequency:"monthly" as const,priority:.8})),...sports.map(sport=>({url:`${base}/sports/${sport.slug}`,changeFrequency:"monthly" as const,priority:.7}))];
}
