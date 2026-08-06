import type { Metadata } from "next";
import { ProductPage } from "../../components/ProductPage";
export const metadata: Metadata = { title: "FAST Scout", description: "The planned FAST scouting workspace for structured player observation, reports, shortlists and connected organisation context." };
export default function Scout(){ return <ProductPage slug="scout"/>; }
