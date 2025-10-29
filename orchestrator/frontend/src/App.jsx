import { useState, useEffect } from 'react';
import { ConfigProvider, theme as antTheme, Steps, Button, Card, Result, Spin } from 'antd';
import { CheckCircleOutlined, DashboardOutlined } from '@ant-design/icons';
import SystemValidation from './components/SystemValidation';
import AdminForm from './components/AdminForm';
import AppSelection from './components/AppSelection';
import Installation from './components/Installation';
import ContainerManager from './components/ContainerManager';
import './App.css';
import { API_BASE } from './config';

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

  // FIX: Wait for auth session before testing protected endpoints
  useEffect(() => {
    const verifyState = async () => {
      try {
        const setupRes = await fetch(`${API_BASE}/setup/status`);
        const setupData = await setupRes.json();

        if (setupData.setup_complete) {
          setSetupComplete(true);
          const { domain, port } = setupData.config.network;
          setDashboardUrl(`http://${domain}:${port}/home`);

          // FIX: Check auth status endpoint first (unprotected)
          const authRes = await fetch(`${API_BASE}/auth/status`, {
            credentials: 'include'
          });

          if (authRes.ok) {
            const authData = await authRes.json();

            if (authData.authenticated) {
              // Session confirmed, now test protected endpoint with retry
              const authenticated = await testProtectedEndpointWithRetry();
              setIsAuthenticated(authenticated);
            } else {
              // Not authenticated, redirect to login
              setIsAuthenticated(false);
            }
          } else {
            setIsAuthenticated(false);
          }
        }
      } catch (err) {
        console.error('State verification failed:', err);
      } finally {
        setAuthChecked(true);
      }
    };

    verifyState();
  }, []);

  // FIX: Retry logic for 401 errors (handles session cookie timing)
  const testProtectedEndpointWithRetry = async (maxRetries = 3) => {
    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        const testRes = await fetch(`${API_BASE}/supos/status`, {
          credentials: 'include'
        });

        if (testRes.ok) {
          return true; // Success
        }

        if (testRes.status === 401 && attempt < maxRetries - 1) {
          // Wait before retry (exponential backoff)
          await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
          continue;
        }

        return false; // Failed after retries
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

  if (showInstallSuccess) {
    return (
      <ConfigProvider theme={{ algorithm: isDark ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm }}>
        <div className="App">
          <Result
            status="success"
            title="supOS-bedrock Installed!"
            subTitle="Your platform is ready. Manage containers below or access the dashboard."
            extra={[
              <Button type="primary" icon={<DashboardOutlined />} href={dashboardUrl} target="_blank" key="dashboard">
                Open supOS Dashboard
              </Button>,
              <Button key="manage" onClick={() => setShowInstallSuccess(false)}>
                Manage Containers
              </Button>,
            ]}
          />
        </div>
      </ConfigProvider>
    );
  }

  if (setupComplete) {
    return (
      <ConfigProvider theme={{ algorithm: isDark ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm }}>
        <div className="App">
          <ContainerManager dashboardUrl={dashboardUrl} />
        </div>
      </ConfigProvider>
    );
  }

  return (
    <ConfigProvider theme={{ algorithm: isDark ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm }}>
      <div className="App">
        <Card style={{ maxWidth: 1000, margin: '40px auto', padding: '20px' }}>
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
            />
          )}
        </Card>
      </div>
    </ConfigProvider>
  );
}

export default App;
