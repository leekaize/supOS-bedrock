import { useState, useEffect } from 'react';
import { ConfigProvider, theme as antTheme, Steps, Button, Card, Result } from 'antd';
import { CheckCircleOutlined } from '@ant-design/icons';
import SystemValidation from './components/SystemValidation';
import AdminForm from './components/AdminForm';
import AppSelection from './components/AppSelection';
import Installation from './components/Installation';
import './App.css';

function App() {
  const [current, setCurrent] = useState(0);
  const [validationPassed, setValidationPassed] = useState(false);
  const [adminData, setAdminData] = useState(null);
  const [selectedApps, setSelectedApps] = useState([]);
  const [setupComplete, setSetupComplete] = useState(false);
  const [dashboardUrl, setDashboardUrl] = useState('http://localhost:8088/home');

  // Detect system theme
  const [isDark, setIsDark] = useState(
    window.matchMedia('(prefers-color-scheme: dark)').matches
  );

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e) => setIsDark(e.matches);
    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
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
  };

  // supOS theme tokens
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

  if (setupComplete) {
    return (
      <ConfigProvider theme={themeConfig}>
        <div className="app-container">
          <Result
            status="success"
            title="supOS-CE Ready"
            subTitle="Setup complete. Redirecting to dashboard..."
            extra={[
              <Button type="primary" key="dashboard" href={dashboardUrl}>
                Go to Dashboard
              </Button>,
            ]}
          />
        </div>
      </ConfigProvider>
    );
  }

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
