import React from 'react';

const ToggleSwitch = ({ id, checked, onChange, label }) => {
  return (
    <div className="flex items-center">
      <div className="onoffswitch">
        <input
          type="checkbox"
          name={`onoffswitch-${id}`}
          className="onoffswitch-checkbox"
          id={`switch-${id}`}
          checked={checked}
          onChange={onChange}
          tabIndex="0"
        />
        <label className="onoffswitch-label" htmlFor={`switch-${id}`} />
      </div>
      {label && <span className="ml-3 text-sm font-medium text-gray-900">{label}</span>}
    </div>
  );
};

export default ToggleSwitch;
