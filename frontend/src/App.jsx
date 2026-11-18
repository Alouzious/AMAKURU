import { Navigate, Route, Routes } from "react-router-dom";
import TenantLayout from "@/layouts/TenantLayout";
import AnswersPage from "@/pages/AnswersPage";
import AuditPage from "@/pages/AuditPage";
import BillingPage from "@/pages/BillingPage";
import ChannelsPage from "@/pages/ChannelsPage";
import ConnectorsPage from "@/pages/ConnectorsPage";
import ConversationDetailPage from "@/pages/ConversationDetailPage";
import ConversationsPage from "@/pages/ConversationsPage";
import EvaluationPage from "@/pages/EvaluationPage";
import ExpiringPage from "@/pages/ExpiringPage";
import GapsPage from "@/pages/GapsPage";
import HomePage from "@/pages/HomePage";
import OnboardPage from "@/pages/OnboardPage";
import OverviewPage from "@/pages/OverviewPage";
import ReviewPage from "@/pages/ReviewPage";
import SearchesPage from "@/pages/SearchesPage";
import SettingsPage from "@/pages/SettingsPage";
import TeamPage from "@/pages/TeamPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/onboard" element={<OnboardPage />} />
      <Route path="/t/:tenantId" element={<TenantLayout />}>
        <Route index element={<OverviewPage />} />
        <Route path="answers" element={<AnswersPage />} />
        <Route path="review" element={<ReviewPage />} />
        <Route path="expiring" element={<ExpiringPage />} />
        <Route path="gaps" element={<GapsPage />} />
        <Route path="searches" element={<SearchesPage />} />
        <Route path="connectors" element={<ConnectorsPage />} />
        <Route path="conversations" element={<ConversationsPage />} />
        <Route path="conversations/:id" element={<ConversationDetailPage />} />
        <Route path="evaluation" element={<EvaluationPage />} />
        <Route path="channels" element={<ChannelsPage />} />
        <Route path="team" element={<TeamPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="billing" element={<BillingPage />} />
        <Route path="audit" element={<AuditPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
