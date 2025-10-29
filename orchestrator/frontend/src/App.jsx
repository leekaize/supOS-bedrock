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

  // Single mount check
  useEffect(() => {
    const verifyState = async () => {
      try {
        const setupRes = await fetch(`${API_BASE}/setup/status`);
        const setupData = await setupRes.json();

        if (setupData.setup_complete) {
          setSetupComplete(true);
          const { domain, port } = setupData.config.network;
          setDashboardUrl(`http://${domain}:${port}/home`);

          // CRITICAL: Test actual protected endpoint, not just auth status
          try {
            const testRes = await fetch(`${API_BASE}/supos/status`, {
              credentials: 'include'
            });
            setIsAuthenticated(testRes.ok); // 200 = auth works, 401 = needs login
          } catch {
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
    },
  ];

  const next = () => setCurrent(current + 1);
  const prev = () => setCurrent(current - 1);

  const handleValidationComplete = (passed) => {
    setValidationPassed(passed);
    if (passed) next();
  };

  const handleAdminComplete = (data) => {
    setAdminData(data);
    next();
  };

  const handleAppSelection = (apps) => {
    setSelectedApps(apps);
    next();
  };

  const handleInstallComplete = (accessUrl) => {
    if (accessUrl) {
      setDashboardUrl(accessUrl);
    }
    setSetupComplete(true);
    setShowInstallSuccess(true);
  };

  const themeConfig = {
    algorithm: isDark ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
    token: {
      colorPrimary: '#1d77fe',
      colorSuccess: '#24a148',
      colorWarning: '#f1c21b',
      colorError: '#da1e28',
      fontFamily: "'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      borderRadius: 4,
    },
  };

  // Block until checks complete
  if (!authChecked) {
    return (
      <ConfigProvider theme={themeConfig}>
        <div className="app-container" style={{ textAlign: 'center', paddingTop: '20%' }}>
          <Spin size="large" />
        </div>
      </ConfigProvider>
    );
  }

  // Require auth after setup
  if (setupComplete && !isAuthenticated) {
    window.location.href = '/login';
    return null;
  }

  // Success page (one-time)
  if (setupComplete && showInstallSuccess) {
    return (
      <ConfigProvider theme={themeConfig}>
        <div className="app-container">
          <Result
            status="success"
            title="Installation Complete"
            subTitle="Your supOS industrial platform is ready"
            extra={[
              <Button
                type="primary"
                size="large"
                icon={<DashboardOutlined />}
                href={dashboardUrl}
                key="dashboard"
              >
                Open supOS Dashboard
              </Button>,
              <Button
                size="large"
                onClick={() => {
                  setShowInstallSuccess(false);
                  window.location.href = '/login';
                }}
                key="orchestrator"
              >
                Manage Containers
              </Button>
            ]}
          />
        </div>
      </ConfigProvider>
    );
  }

  // Container management (authenticated)
  if (setupComplete && isAuthenticated) {
    return (
      <ConfigProvider theme={themeConfig}>
        <div className="app-container">
          <div className="wizard-header">
            <h1>supOS-bedrock</h1>
          </div>
          <Card className="wizard-card">
            <ContainerManager />
          </Card>
        </div>
      </ConfigProvider>
    );
  }

  // Setup wizard
  return (
    <ConfigProvider theme={themeConfig}>
      <div className="app-container">
        <div className="wizard-header">
          <h1>supOS-CE Setup</h1>
          <p>Configure your industrial IoT platform in 4 steps</p>
        </div>

        <Card className="wizard-card">
          <Steps current={current} items={steps} className="wizard-steps" />

          <div className="steps-content">
            {current === 0 && (
              <SystemValidation onComplete={handleValidationComplete} />
            )}
            {current === 1 && (
              <AdminForm onComplete={handleAdminComplete} onBack={prev} />
            )}
            {current === 2 && (
              <AppSelection
                selectedApps={selectedApps}
                onComplete={handleAppSelection}
                onBack={prev}
              />
            )}
            {current === 3 && (
              <Installation
                adminData={adminData}
                selectedApps={selectedApps}
                onComplete={handleInstallComplete}
                onBack={prev}
              />
            )}
          </div>
        </Card>
      </div>
    </ConfigProvider>
  );
}

export default App;
