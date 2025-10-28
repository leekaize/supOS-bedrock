import { useState, useEffect, useRef } from 'react';
import { Button, Typography, Steps, Alert, Spin, Progress, Modal } from 'antd';
import { CheckCircleOutlined, LoadingOutlined, CloseCircleOutlined, FileTextOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Title, Text } = Typography;
import { API_BASE } from '../config';

// More granular steps based on actual installation stages
const installSteps = [
  { key: 'init', title: 'Initialization', keywords: ['Configuration saved', 'Installation started'] },
  { key: 'volumes', title: 'Creating Volumes', keywords: ['creating volumes', 'init-volumes', 'loading npm cache'] },
  { key: 'containers', title: 'Starting Containers', keywords: ['Starting Docker containers', 'Container', 'Creating', 'Started'] },
  { key: 'services', title: 'Initializing Services', keywords: ['init nodered', 'init eventflow', 'init minio', 'init portainer'] },
  { key: 'complete', title: 'Finalizing', keywords: ['All services are up', 'Installation complete'] }
];

function Installation({ adminData, selectedApps, onComplete, onBack }) {
  const [currentStep, setCurrentStep] = useState(0);
  const [status, setStatus] = useState('running');
  const [progress, setProgress] = useState(0);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState(null);
  const [showFullLogs, setShowFullLogs] = useState(false);
  const [lastLogLine, setLastLogLine] = useState(0);
  const [accessUrl, setAccessUrl] = useState('');
  const logContainerRef = useRef(null);
  const pollIntervalRef = useRef(null);

  useEffect(() => {
    startInstallation();
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs]);

  const addLog = (message, type = 'info') => {
    setLogs(prev => [...prev, { message, type, timestamp: new Date().toISOString() }]);
  };

  const detectStageFromLog = (logText) => {
    const lowerLog = logText.toLowerCase();

    for (let i = 0; i < installSteps.length; i++) {
      const step = installSteps[i];
      if (step.keywords.some(keyword => lowerLog.includes(keyword.toLowerCase()))) {
        return i;
      }
    }
    return null;
  };

  const calculateProgress = (step, logText) => {
    // Base progress per step
    const baseProgress = [0, 15, 40, 70, 95];
    let stepProgress = baseProgress[step] || 0;

    // Fine-tune within Container step based on container count
    if (step === 2) {
      const containerMatch = logText.match(/Container\s+\w+\s+(Creating|Created|Starting|Started|Healthy)/gi);
      if (containerMatch) {
        const containerEvents = containerMatch.length;
        stepProgress += Math.min(containerEvents * 1.5, 25);
      }
    }

    return Math.min(stepProgress, 99); // Never reach 100 until complete
  };

  const pollLogs = async (dashboardUrl) => {
    try {
      const response = await axios.get(`${API_BASE}/install/logs/stream?from=${lastLogLine}`);

      if (response.data.lines && response.data.lines.length > 0) {
        const newLines = response.data.lines;

        newLines.forEach(line => {
          const trimmed = line.trim();
          if (!trimmed) return;

          // Detect log type
          let type = 'info';
          if (trimmed.includes('✓') || trimmed.includes('successfully') || trimmed.includes('success')) {
            type = 'success';
          } else if (trimmed.includes('[ERROR]') || trimmed.includes('Failed') || trimmed.includes('✗')) {
            type = 'error';
          } else if (trimmed.includes('[WARN]')) {
            type = 'warning';
          }

          addLog(trimmed, type);

          // Update step based on log content
          const detectedStep = detectStageFromLog(trimmed);
          let activeStep = currentStep;
          if (detectedStep !== null && detectedStep > currentStep) {
            setCurrentStep(detectedStep);
            activeStep = detectedStep; // Use new step immediately
          }

          // Update progress using active step (not stale state)
          const newProgress = calculateProgress(activeStep, trimmed);
          setProgress(prev => Math.max(prev, newProgress));
        });

        setLastLogLine(response.data.current_line);
      }

      // Check if installation completed
      if (response.data.completed) {
        setProgress(100);
        setCurrentStep(installSteps.length - 1);
        setStatus('success');
        addLog('✓ Installation complete!', 'success');

        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
        }

        setTimeout(() => onComplete(dashboardUrl), 2000);
      }

      // Check for errors
      if (response.data.failed) {
        setStatus('error');
        setError('Installation failed. Check logs for details.');
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
        }
      }

    } catch (err) {
      console.error('Poll error:', err);
      // Don't stop polling on network errors - installation might still be running
    }
  };

  const startInstallation = async () => {
    try {
      addLog('Preparing configuration...');
      setProgress(5);

      const networkConfig = {
        domain: window.location.hostname,
        port: 8088
      };

      // Store access URL for completion callback
      const url = `http://${networkConfig.domain}:${networkConfig.port}/home`;
      setAccessUrl(url);  // Save to state for display

      // Start installation (returns immediately)
      const installResponse = await axios.post(`${API_BASE}/install/start`, {
        selected_apps: selectedApps,
        admin: adminData,
        network: networkConfig
      });

      if (!installResponse.data.success) {
        throw new Error(installResponse.data.error || 'Installation failed to start');
      }

      addLog('Installation started, streaming logs...', 'success');
      setProgress(10);

      // Start polling for logs every 2 seconds
      pollIntervalRef.current = setInterval(() => pollLogs(url), 2000);

    } catch (err) {
      setStatus('error');
      setError(err.message);
      addLog(`✗ Error: ${err.message}`, 'error');
    }
  };

  const openFullLogs = () => {
    window.open(`${API_BASE}/install/logs`, '_blank');
  };

  return (
    <div>
      <Title level={3}>Installing supOS Platform</Title>
      <Text type="secondary">This may take 3-5 minutes. Progress updates in real-time.</Text>

      <Steps
        current={currentStep}
        status={status === 'error' ? 'error' : 'process'}
        items={installSteps}
        style={{ margin: '30px 0' }}
      />

      <Progress
        percent={Math.round(progress)}
        status={status === 'error' ? 'exception' : status === 'success' ? 'success' : 'active'}
        style={{ marginBottom: 20 }}
      />

      {error && (
        <Alert
          message="Installation Failed"
          description={error}
          type="error"
          showIcon
          icon={<CloseCircleOutlined />}
          style={{ marginBottom: 20 }}
        />
      )}

      <div style={{ marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text strong>Installation Logs</Text>
        <Button
          size="small"
          icon={<FileTextOutlined />}
          onClick={openFullLogs}
        >
          View Full Logs
        </Button>
      </div>

      <div
        ref={logContainerRef}
        style={{
          background: '#000',
          color: '#0f0',
          padding: 20,
          borderRadius: 4,
          fontFamily: 'monospace',
          fontSize: 13,
          maxHeight: 300,
          overflowY: 'auto',
          border: '1px solid #333'
        }}
      >
        {logs.length === 0 && status === 'running' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#888' }}>
            <Spin indicator={<LoadingOutlined style={{ color: '#0f0' }} spin />} />
            <span>Waiting for logs...</span>
          </div>
        )}
        {logs.map((log, idx) => (
          <div key={idx} style={{
            color: log.type === 'error' ? '#f00' : log.type === 'success' ? '#0f0' : log.type === 'warning' ? '#ff0' : '#ccc',
            marginBottom: 4
          }}>
            {log.message}
          </div>
        ))}
        {status === 'running' && logs.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
            <Spin indicator={<LoadingOutlined style={{ color: '#0f0' }} spin />} />
            <span>Processing...</span>
          </div>
        )}
      </div>

      {status === 'error' && (
        <div style={{ marginTop: 20, display: 'flex', gap: 10 }}>
          <Button onClick={onBack}>Back to Configuration</Button>
          <Button type="primary" onClick={openFullLogs}>View Full Logs</Button>
        </div>
      )}
    </div>
  );
}

export default Installation;
