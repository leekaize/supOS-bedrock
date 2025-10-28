import { useState } from 'react';
import { Steps, Button, Card, Result, Space } from 'antd';
import { CheckCircleOutlined, LoadingOutlined } from '@ant-design/icons';
import SystemValidation from './components/SystemValidation';
import AdminForm from './components/AdminForm';
import AppSelection from './components/AppSelection';
import Installation from './components/Installation';
import './App.css';

const { Step } = Steps;

function App() {
  const [current, setCurrent] = useState(0);
  const [validationPassed, setValidationPassed] = useState(false);
  const [adminData, setAdminData] = useState(null);
  const [selectedApps, setSelectedApps] = useState([]);
  const [setupComplete, setSetupComplete] = useState(false);
  const [dashboardUrl, setDashboardUrl] = useState('http://localhost:8088/home');

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

  const next = () => {
    setCurrent(current + 1);
  };

  const prev = () => {
    setCurrent(current - 1);
  };

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

  if (setupComplete) {
    return (
      <div className="app-container">
        <Result
          status="success"
          title="supOS Platform Ready"
          subTitle="Setup complete. Redirecting to dashboard..."
          extra={[
            <Button type="primary" key="dashboard" href={dashboardUrl}>
              Go to Dashboard
            </Button>,
          ]}
        />
      </div>
    );
  }

  return (
    <div className="app-container">
      <div className="wizard-header">
        <h1>supOS Platform Setup</h1>
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
  );
}

export default App;
