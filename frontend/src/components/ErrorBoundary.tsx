import { Component, ReactNode } from 'react';
import { Alert, Card, CardContent, Typography, Button } from '@mui/material';

interface Props {
    children: ReactNode;
    fallbackMessage?: string;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

export class ChartErrorBoundary extends Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, info: React.ErrorInfo): void {
        console.error('[ChartErrorBoundary]', error, info.componentStack);
    }

    handleReset = (): void => {
        this.setState({ hasError: false, error: null });
    };

    render(): ReactNode {
        if (this.state.hasError) {
            return (
                <Card>
                    <CardContent>
                        <Typography variant="h6" gutterBottom>
                            Erreur d'affichage
                        </Typography>
                        <Alert severity="error" sx={{ mb: 2 }}>
                            {this.props.fallbackMessage ?? 'Le graphique n\'a pas pu être affiché.'}
                        </Alert>
                        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                            {this.state.error?.message}
                        </Typography>
                        <Button variant="outlined" size="small" onClick={this.handleReset}>
                            Réessayer
                        </Button>
                    </CardContent>
                </Card>
            );
        }

        return this.props.children;
    }
}
