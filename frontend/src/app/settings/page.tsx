"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Network, Percent, Building2, FileText } from "lucide-react";
import IntegrationsTab from "@/components/settings/IntegrationsTab";
import MarginsTab from "@/components/settings/MarginsTab";
import CompanyTab from "@/components/settings/CompanyTab";
import TemplateTab from "@/components/settings/TemplateTab";
import { useAuth } from "@/lib/auth-context";

const TABS = [
  { id: "integrations", label: "Integrări API", icon: Network },
  { id: "margins", label: "Marje și Prețuri", icon: Percent },
  { id: "company", label: "Companie", icon: Building2 },
  { id: "template", label: "Template Ofertă", icon: FileText },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabId>("integrations");
  const { isAdmin, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAdmin) {
      router.replace("/chat");
    }
  }, [isLoading, isAdmin, router]);

  if (isLoading || !isAdmin) {
    return null;
  }

  return (
    <div className="h-full overflow-y-auto p-3 sm:p-6 lg:p-8">
      <div className="max-w-5xl mx-auto space-y-4 sm:space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-dark-50">Setări</h1>
          <p className="text-xs sm:text-sm text-dark-200 mt-1">
            Gestionează integrările, marjele, datele companiei și template-urile
          </p>
        </div>

        {/* Tab Navigation */}
        <div className="flex gap-1 p-1 rounded-2xl bg-dark-500/30 border border-[rgba(255,255,255,0.06)] w-full sm:w-fit overflow-x-auto scrollbar-hide">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`relative flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-colors ${
                  isActive
                    ? "text-dark-50"
                    : "text-dark-300 hover:text-dark-100"
                }`}
              >
                {isActive && (
                  <motion.div
                    layoutId="settings-tab-bg"
                    className="absolute inset-0 rounded-xl bg-dark-400/40 border border-[rgba(255,255,255,0.08)]"
                    transition={{ type: "spring", duration: 0.4, bounce: 0.15 }}
                  />
                )}
                <span className="relative z-10 flex items-center gap-2 whitespace-nowrap">
                  <Icon size={16} />
                  <span className="hidden sm:inline">{tab.label}</span>
                </span>
              </button>
            );
          })}
        </div>

        {/* Tab Content */}
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
        >
          {activeTab === "integrations" && <IntegrationsTab />}
          {activeTab === "margins" && <MarginsTab />}
          {activeTab === "company" && <CompanyTab />}
          {activeTab === "template" && <TemplateTab />}
        </motion.div>
      </div>
    </div>
  );
}
