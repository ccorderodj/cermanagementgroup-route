import { Suspense } from 'react';
import { AppMainContent } from './providers/maincontent';

const App = () => {
    return (
        <Suspense fallback="">
            <AppMainContent />
        </Suspense>
    );
};

export default App;
