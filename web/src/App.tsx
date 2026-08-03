
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { LanguageProvider } from "./context/LanguageContext";
import Index from "./pages/Index";
import PlannerPage from "./pages/PlannerPage";
import ProfilePage from "./pages/ProfilePage";
import BeautyPlatformPage from "./pages/BeautyPlatformPage";
import NotFound from "./pages/NotFound";
import TravelChallengesPage from "./pages/TravelChallengesPage";
import TestFamilyTree from "./pages/TestFamilyTree";
import BasicTest from "./pages/BasicTest";
import MafiaGamePage from "./features/mafia-game/MafiaGamePage";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <LanguageProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Index />} />
            <Route path="/planner" element={<PlannerPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/beauty-platform" element={<BeautyPlatformPage />} />
            <Route path="/challenges" element={<TravelChallengesPage />} />
            <Route path="/challenges/:challengeId" element={<TravelChallengesPage />} />
            <Route path="/game" element={<MafiaGamePage />} />
            <Route path="/test-family-tree" element={<TestFamilyTree />} />
            <Route path="/basic-test" element={<BasicTest />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </LanguageProvider>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
