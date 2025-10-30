import { useState, useEffect } from 'react';
import { ConfigProvider, theme as antTheme, Steps, Button, Card, Result, Spin, Typography } from 'antd';
import { CheckCircleOutlined, DashboardOutlined } from '@ant-design/icons';
import SystemValidation from './components/SystemValidation';
import AdminForm from './components/AdminForm';
import AppSelection from './components/AppSelection';
import Installation from './components/Installation';
import ContainerManager from './components/ContainerManager';
import './App.css';
import { API_BASE } from './config';

const { Title } = Typography;

function App() {
  const [current, setCurrent] = useState(0);
  const [validationPassed, setValidationPassed] = useState(false);
  const [adminData, setAdminData] = useState(null);
  const [selectedApps, setSelectedApps] = useState([]);
  const [setupComplete, setSetupComplete] = useState(false);
  const [dashboardUrl, setDashboardUrl] = useState('http://localhost:8088/home');
  const [showInstallSuccess, setShowInstallSuccess] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  const [isDark, setIsDark] = useState(
    window.matchMedia('(prefers-color-scheme: dark)').matches
  );

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e) => setIsDark(e.matches);
    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, []);

  useEffect(() => {
    const verifyState = async () => {
      try {
        const setupRes = await fetch(`${API_BASE}/setup/status`);

        if (!setupRes.ok) {
          throw new Error(`Status check failed: ${setupRes.status}`);
        }

        const setupData = await setupRes.json();

        if (!setupData.setup_complete) {
          setSetupComplete(false);
          setIsAuthenticated(false);
          setAuthChecked(true);
          return;
        }

        setSetupComplete(true);
        const { domain, port } = setupData.config.network;
        setDashboardUrl(`http://${domain}:${port}/home`);

        // Poll for session establishment (handles cookie timing)
        let authenticated = false;
        for (let attempt = 0; attempt < 5; attempt++) {
          const sessionCheck = await fetch(`${API_BASE}/auth/session-check`, {
            credentials: 'include'
          });

          if (sessionCheck.ok) {
            const sessionData = await sessionCheck.json();

            if (sessionData.session_established) {
              authenticated = await testProtectedEndpointWithRetry();
              if (authenticated) break; // Success
            }
          }

          // Wait before retry
          if (attempt < 4) await new Promise(r => setTimeout(r, 800));
        }

        setIsAuthenticated(authenticated);

      } catch (err) {
        console.error('State verification failed:', err);
        setSetupComplete(false);
        setIsAuthenticated(false);
      } finally {
        setAuthChecked(true);
      }
    };

    verifyState();
  }, []);

  const testProtectedEndpointWithRetry = async (maxRetries = 3) => {
    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        const testRes = await fetch(`${API_BASE}/supos/status`, {
          credentials: 'include'
        });

        if (testRes.ok) {
          return true;
        }

        if (testRes.status === 401 && attempt < maxRetries - 1) {
          await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
          continue;
        }

        return false;
      } catch (err) {
        console.error(`Attempt ${attempt + 1} failed:`, err);
        if (attempt < maxRetries - 1) {
          await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
        }
      }
    }
    return false;
  };

  const steps = [
    {
      title: 'System Check',
      icon: validationPassed ? <CheckCircleOutlined /> : null,
    },
    {
      title: 'Admin Account',
      icon: adminData ? <CheckCircleOutlined /> : null,
    },
    {
      title: 'Select Apps',
      icon: selectedApps.length > 0 ? <CheckCircleOutlined /> : null,
    },
    {
      title: 'Installation',
      icon: setupComplete ? <CheckCircleOutlined /> : null,
    },
  ];

  const handleValidationComplete = (passed) => {
    setValidationPassed(passed);
    if (passed) setCurrent(1);
  };

  const handleAdminComplete = (data) => {
    setAdminData(data);
    setCurrent(2);
  };

  const handleAppSelectionComplete = (apps) => {
    setSelectedApps(apps);
    setCurrent(3);
  };

  const handleInstallationComplete = (success) => {
    if (success) {
      setSetupComplete(true);
      setShowInstallSuccess(true);
    }
  };

  if (!authChecked) {
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh'
      }}>
        <Spin size="large" />
      </div>
    );
  }

  // Setup complete + authenticated = show Container Manager
  if (setupComplete && isAuthenticated) {
    return (
      <ConfigProvider theme={{ algorithm: isDark ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm }}>
        <div className="App">
          <ContainerManager dashboardUrl={dashboardUrl} />
        </div>
      </ConfigProvider>
    );
  }

  // Setup complete + NOT authenticated = require login
  if (setupComplete && !isAuthenticated) {
    return (
      <ConfigProvider theme={{ algorithm: isDark ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm }}>
        <div className="App">
          <Result
            status="warning"
            title="Authentication Required"
            subTitle="Please log in to access the orchestrator"
            extra={
              <Button type="primary" href="/login">
                Log In
              </Button>
            }
          />
        </div>
      </ConfigProvider>
    );
  }

  // Post-installation success
  if (showInstallSuccess) {
    return (
      <ConfigProvider theme={{ algorithm: isDark ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm }}>
        <div className="App">
          <Result
            status="success"
            title="Installation Complete!"
            subTitle="supOS Bedrock is ready"
            extra={[
              <Button
                type="primary"
                key="dashboard"
                icon={<DashboardOutlined />}
                onClick={() => window.open(dashboardUrl, '_blank')}
              >
                Open supOS Dashboard
              </Button>,
              <Button key="orchestrator" onClick={() => window.location.href = '/login'}>
                Go to Orchestrator
              </Button>
            ]}
          />
        </div>
      </ConfigProvider>
    );
  }

  // Default: Setup wizard
  return (
    <ConfigProvider theme={{ algorithm: isDark ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm }}>
      <div className="App">
        <Card style={{ maxWidth: 1000, margin: '40px auto', padding: '20px' }}>
          <Title level={2}>supOS Bedrock Setup</Title>
          <Steps current={current} items={steps} style={{ marginBottom: 40 }} />

          {current === 0 && <SystemValidation onComplete={handleValidationComplete} />}
          {current === 1 && <AdminForm onComplete={handleAdminComplete} onBack={() => setCurrent(0)} />}
          {current === 2 && (
            <AppSelection
              selectedApps={selectedApps}
              onComplete={handleAppSelectionComplete}
              onBack={() => setCurrent(1)}
            />
          )}
          {current === 3 && (
            <Installation
              adminData={adminData}
              selectedApps={selectedApps}
              onComplete={handleInstallationComplete}
              onBack={() => setCurrent(2)}
            />
          )}
        </Card>
      </div>
    </ConfigProvider>
  );
}

export default App;
