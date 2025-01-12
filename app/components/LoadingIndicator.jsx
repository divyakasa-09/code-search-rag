import React from 'react';
import { Card } from '@/components/ui/card';

const LoadingIndicator = () => {
  return (
    <Card className="w-full max-w-xl mx-auto p-6 space-y-4">
      <div className="text-center">
        <h2 className="text-xl font-semibold mb-4">Loading Code Repository Assistant</h2>
        <div className="w-full bg-gray-200 rounded-full h-2.5">
          <div className="bg-blue-600 h-2.5 rounded-full animate-[loading_2s_ease-in-out_infinite]" 
               style={{width: '90%'}}></div>
        </div>
        <p className="mt-4 text-gray-600">Initializing services and loading repositories...</p>
      </div>
    </Card>
  );
};

export default LoadingIndicator;