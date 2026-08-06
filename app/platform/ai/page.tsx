import type { Metadata } from "next";
import { ProductPage } from "../../components/ProductPage";
export const metadata: Metadata = { title: "FAST AI", description: "The future FAST intelligence layer for assisted discovery, search, workflow support and analyst-led review." };
export default function AI(){ return <ProductPage slug="ai"/>; }
