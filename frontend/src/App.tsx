import { QueryClientProvider } from '@tanstack/react-query';
import { Onborda, OnbordaProvider } from 'onborda';
import { useMemo } from 'react';
import { createBrowserRouter, Navigate, RouterProvider, useNavigate } from 'react-router-dom';

import { MCPHubPage } from './pages/mcp';
import { SkillHubPage } from './pages/skill';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { RouteError } from '@/components/error/RouteError';
import { buildChatTour } from '@/components/tour/chatTourSteps';
import { TourCard } from '@/components/tour/TourCard';
import { Toaster } from '@/components/ui/sonner';
import { AuthProvider } from '@/context/AuthContext';
import { useTranslation } from '@/i18n/useI18n';
import { queryClient } from '@/lib/query-client';
import { AuthPage } from '@/pages/auth';
import { ChannelPage } from '@/pages/channel';
import { ChatPage } from '@/pages/chat';
import { CredentialPage } from '@/pages/credential';
import { KnowledgePage } from '@/pages/knowledge';
import { SchedulePage } from '@/pages/schedule';
import { SetupPage } from '@/pages/setup';
import { VoiceProfilePage } from '@/pages/voice-profile';

function SetupPageRoute() {
	const navigate = useNavigate();
	return (
		<>
			<div className="h-screen">
				<SetupPage onComplete={() => navigate('/login')} />
			</div>
		</>
	);
}

const router = createBrowserRouter([
	{
		element: <RequireAuth />,
		errorElement: <RouteError />,
		children: [
			{
				// Content-level boundary: a crash in a page replaces only
				// the Outlet area, so AppLayout (the icon rail / nav) stays
				// usable. The parent route keeps its own errorElement as a
				// last-resort catch-all for AppLayout/AppSidebar crashes.
				errorElement: <RouteError />,
				children: [
					{ path: '/', element: <Navigate to="/chat" replace /> },
					{
						path: '/chat/:agentId?/:sessionId?/:memberId?',
						element: <ChatPage />,
					},
					{ path: '/schedule', element: <SchedulePage /> },
					{ path: '/channel', element: <ChannelPage /> },
					{ path: '/credential', element: <CredentialPage /> },
					{ path: '/voice-profile', element: <VoiceProfilePage /> },
					{ path: '/mcp', element: <MCPHubPage /> },
					{ path: '/mcp/:hubId', element: <MCPHubPage /> },
					{ path: '/skill', element: <SkillHubPage /> },
					{ path: '/skill/:hubId', element: <SkillHubPage /> },
					{ path: '/knowledge', element: <KnowledgePage /> },
					{ path: '/knowledge/:kbId', element: <KnowledgePage /> },
				],
			},
		],
	},
	{ path: '/setup', element: <SetupPageRoute />, errorElement: <RouteError /> },
	{ path: '/login', element: <AuthPage key="login" />, errorElement: <RouteError /> },
	{
		path: '/register',
		element: <AuthPage key="register" register />,
		errorElement: <RouteError />,
	},
]);

function App() {
	const { t } = useTranslation();
	const tours = useMemo(() => [buildChatTour(t)], [t]);

	return (
		<QueryClientProvider client={queryClient}>
			<AuthProvider>
				<OnbordaProvider>
					<Onborda
						steps={tours}
						cardComponent={TourCard}
						shadowOpacity="0.6"
						cardTransition={{ type: 'spring', duration: 0.4 }}
					>
						<RouterProvider router={router} />
						<Toaster richColors position="top-right" />
					</Onborda>
				</OnbordaProvider>
			</AuthProvider>
		</QueryClientProvider>
	);
}

export default App;
