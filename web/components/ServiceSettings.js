import React, { useState } from 'react';
import { 
  Save,
  AlertCircle,
  Server,
  Clock,
  Bell,
  Cog,
  Terminal
} from 'lucide-react';
import ToggleSwitch from './ToggleSwitch';

const ServiceSettings = () => {
  const [activeTab, setActiveTab] = useState('jellyfin');
  const [isDirty, setIsDirty] = useState(false);
  const [serviceStates, setServiceStates] = useState({
    jellyfin: true,
    plex: false,
    sonarr: true,
    radarr: true,
    nextcloud: true,
    system: true
  });

  const [settings, setSettings] = useState({
    jellyfin: {
      apiKey: '',
      url: 'http://localhost:8096',
      timeout: 10
    },
    plex: {
      token: '',
      url: 'http://localhost:32400',
      monitorTranscoding: true,
      ignorePaused: false,
      timeout: 10
    },
    sonarr: {
      apiKey: '',
      url: 'http://localhost:8989',
      timeout: 10
    },
    radarr: {
      apiKey: '',
      url: 'http://localhost:7878',
      timeout: 10
    },
    nextcloud: {
      url: 'http://localhost:9000',
      token: '',
      cpuThreshold: 0.5,
      timeout: 10
    },
    system: {
      ignoreUsers: [],
      loadThreshold: 0.5,
      checkLoad: true
    }
  });

  const tabs = [
    { id: 'jellyfin', name: 'Jellyfin', icon: Server },
    { id: 'plex', name: 'Plex', icon: Server },
    { id: 'sonarr', name: 'Sonarr', icon: Bell },
    { id: 'radarr', name: 'Radarr', icon: Bell },
    { id: 'nextcloud', name: 'Nextcloud', icon: Terminal },
    { id: 'system', name: 'System', icon: Cog }
  ];

  const handleSave = () => {
    // TODO: Implement save functionality
    setIsDirty(false);
  };

  const handleInputChange = (service, field, value) => {
    setSettings(prev => ({
      ...prev,
      [service]: {
        ...prev[service],
        [field]: value
      }
    }));
    setIsDirty(true);
  };

  const renderServiceSettings = (service) => {
    const showSettings = serviceStates[service];
    if (!showSettings) return null;

    const serviceConfig = settings[service];
    return Object.entries(serviceConfig).map(([field, value]) => {
      if (field === 'ignoreUsers') {
        return (
          <div key={field} className="mt-4">
            <ToggleSwitch
              id={`${service}-${field}`}
              checked={value.length > 0}
              onChange={(e) => handleInputChange(service, field, e.target.checked ? ['default'] : [])}
              label="Ignore Users"
            />
          </div>
        );
      }

      if (typeof value === 'boolean') {
        return (
          <div key={field} className="mt-4">
            <ToggleSwitch
              id={`${service}-${field}`}
              checked={value}
              onChange={(e) => handleInputChange(service, field, e.target.checked)}
              label={field.replace(/([A-Z])/g, ' $1').trim()}
            />
          </div>
        );
      }
      
      return (
        <div key={field} className="mt-4">
          <label className="block text-sm font-medium text-gray-700 capitalize">
            {field.replace(/([A-Z])/g, ' $1').trim()}
          </label>
          <input
            type={field.includes('token') || field.includes('key') ? 'password' : 
                  typeof value === 'number' ? 'number' : 'text'}
            value={value}
            onChange={(e) => {
              const newValue = e.target.type === 'number' ? 
                parseFloat(e.target.value) : e.target.value;
              handleInputChange(service, field, newValue);
            }}
            step={typeof value === 'number' ? '0.1' : undefined}
            min={typeof value === 'number' ? '0' : undefined}
            max={typeof value === 'number' ? '1' : undefined}
            className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>
      );
    });
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="py-6">
          <div className="bg-white shadow rounded-lg overflow-hidden">
            <div className="px-4 sm:px-6 lg:px-8 py-6">
              <div className="sm:flex sm:items-center">
                <div className="sm:flex-auto">
                  <h1 className="text-2xl font-semibold text-gray-900">
                    Service Settings
                  </h1>
                  <p className="mt-2 text-sm text-gray-700">
                    Configure settings and enable/disable services
                  </p>
                </div>
                <div className="mt-4 sm:mt-0 sm:ml-16 sm:flex-none">
                  <button
                    type="button"
                    onClick={handleSave}
                    disabled={!isDirty}
                    className={`inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white ${
                      isDirty 
                        ? 'bg-indigo-600 hover:bg-indigo-700'
                        : 'bg-gray-400 cursor-not-allowed'
                    }`}
                  >
                    <Save className="mr-2 h-4 w-4" />
                    Save Changes
                  </button>
                </div>
              </div>

              <div className="mt-6">
                <div className="border-b border-gray-200 w-full overflow-x-auto no-scrollbar">
                  <nav className="flex min-w-max">
                    <div className="flex space-x-8 py-2">
                      {tabs.map((tab) => {
                        const Icon = tab.icon;
                        return (
                          <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={`
                              ${activeTab === tab.id
                                ? 'border-indigo-500 text-indigo-600 border-b-2'
                                : 'text-gray-500 hover:text-gray-700 hover:border-gray-300'
                              }
                              group inline-flex items-center px-4 py-2 font-medium text-sm whitespace-nowrap
                            `}
                          >
                            <Icon className={`
                              ${activeTab === tab.id ? 'text-indigo-500' : 'text-gray-400 group-hover:text-gray-500'}
                              -ml-0.5 mr-2 h-5 w-5
                            `} />
                            {tab.name}
                          </button>
                        );
                      })}
                    </div>
                  </nav>
                </div>

                <div className="mt-6 p-4">
                  <div className="space-y-6">
                    <div className="mb-6 pb-6 border-b border-gray-200">
                      <div className="flex items-center justify-between">
                        <span className="text-lg font-medium text-gray-900 capitalize">{activeTab}</span>
                        <ToggleSwitch
                          id={activeTab}
                          checked={serviceStates[activeTab]}
                          onChange={(e) => {
                            setServiceStates(prev => ({
                              ...prev,
                              [activeTab]: e.target.checked
                            }));
                            setIsDirty(true);
                          }}
                        />
                      </div>
                    </div>
                    {renderServiceSettings(activeTab)}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ServiceSettings;
