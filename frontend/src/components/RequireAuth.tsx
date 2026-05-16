import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { getApiKey, getAuthToken } from '../api/client';

export const RequireAuth: React.FC<{ children: React.ReactElement }> = ({ children }) => {
  const location = useLocation();

  if (!getAuthToken() && !getApiKey()) {
    const redirect = encodeURIComponent(`${location.pathname}${location.search}`);
    return <Navigate to={`/login?redirect=${redirect}`} replace />;
  }

  return children;
};
